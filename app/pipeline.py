"""The full extraction: image → (crop + flatten) → OCR → parse → result dict. Shared by the API and scripts."""

from __future__ import annotations

import time
from functools import partial

import numpy as np

from .card_core.layout import Document, drop_non_text
from .card_core.pattern_card import build_result, jp_normalize
from .card_core.redact import LABEL_RE as MY_NUMBER_LABEL_RE, redact_my_number, redact_text
from .detect import detect_document
from .driver_license import parse_driver_license, parse_driving_history
from .health_insurance import parse_health_insurance
from .juki_card import parse_juki_card
from .my_number_card import parse_my_number_card
from .passport import parse_passport
from .pension import parse_pension
from .resident_record import parse_resident_record
from .special_permanent import parse_special_permanent
from .ocr import vl_client
from .ocr.ppocr import run_ocr
from .ocr.ppocr_model import model_name
from .preprocess import normalize_card
from .residence_card import MODES, parse_residence_card

ENGINES = ("ppocr", "vl")
# document type -> (parser, OCR language, crop the ID-1 card). Cards share the crop/flatten step; the passport
# photo page is not ID-1 and is usually photographed open (2 pages ≈ same aspect as 1 page), so it is not cropped,
# nor are the full-page / booklet documents (住民票, 年金手帳).
DOCUMENTS = {
    # the user needs only the card number of the residence card (other fields still parsed internally)
    "jp_residence": (partial(parse_residence_card, keys=("card_number",)), "ja", True),
    "jp_mynumber": (parse_my_number_card, "ja", True),
    "jp_driver_license": (parse_driver_license, "ja", True),
    "jp_passport": (parse_passport, "ja", False),
    "jp_health_insurance": (parse_health_insurance, "ja", True),
    "jp_special_permanent": (parse_special_permanent, "ja", True),
    "jp_driving_history": (parse_driving_history, "ja", True),
    "jp_juki_card": (parse_juki_card, "ja", True),
    "jp_resident_record": (parse_resident_record, "ja", False),
    "jp_pension_book": (parse_pension, "ja", False),
}
# Documents on which every 12-digit number is a My Number (masked, card_core.redact); elsewhere only next to 個人番号.
MASK_ALL_12_DIGITS = {"jp_resident_record"}

# document=auto: crop as an ID-1 card, OCR, then detect.py picks the document (all use the "ja" OCR).
AUTO = "auto"
DOCUMENT_CHOICES = (AUTO, *DOCUMENTS)


UNKNOWN_WARNING = (
    "Không nhận diện được loại giấy tờ (không thấy tiêu đề / nhãn / dạng số của loại nào): chỉ trả chữ OCR "
    "(full_text, ocr.lines). Hãy chụp rõ hơn hoặc chọn loại giấy tờ bằng tay."
)


VL_WARNING = (
    "PaddleOCR-VL không trả độ tin cậy theo dòng: needs_review chỉ dựa vào định dạng và kiểm tra chéo, "
    "đánh giá chất lượng ảnh chỉ dựa vào số nhãn đọc được."
)


def extract(
    img: np.ndarray,
    original_size: tuple[int, int],
    crop: bool = True,
    engine: str = "ppocr",
    mode: str = "label",
    document: str = "jp_residence",
) -> tuple[dict, np.ndarray]:
    """Return the result and the processed image its boxes refer to.

    document="auto" detects (or guesses) the document from the OCR text (detect.py) and adds `document_detection`
    to the result. Nothing to go on → no error: `document`/`document_type` null, no fields, the OCR text only.
    Every result carries the `document` that was parsed.

    mode=zone/hybrid need per-line boxes, which only engine=ppocr gives (VL boxes are whole blocks).
    Raises vl_client.VlUnavailable when engine="vl" and the VL service cannot be reached.
    """
    if engine == "vl" and mode != "label":
        raise ValueError("mode=zone/hybrid chỉ hỗ trợ engine=ppocr.")
    t0 = time.perf_counter()
    original = img
    card = DOCUMENTS[document][2] if document != AUTO else True
    cropped = False
    if crop and card:
        img, cropped = normalize_card(img)
    t1 = time.perf_counter()
    lang = DOCUMENTS[document][1] if document != AUTO else "ja"
    boxes, img, deskew, model, vl_resp = _ocr(img, engine, lang)

    detection = None
    if document == AUTO:
        detection = detect_document(boxes)
        document = detection.document
        if document is not None and cropped and not DOCUMENTS[document][2]:  # passport, pages: read the uncropped image
            img, cropped = original, False
            boxes, img, deskew, model, vl_resp = _ocr(img, engine, lang)
    boxes, img, vl_resp, redacted = _redact(boxes, img, vl_resp, document in MASK_ALL_12_DIGITS)
    parse = DOCUMENTS[document][0] if document is not None else _ocr_text_only
    t2 = time.perf_counter()
    h, w = img.shape[:2]
    result = parse(boxes, page_size=(w, h), cropped=cropped, mode=mode)
    t3 = time.perf_counter()
    if vl_resp is not None:
        result["warnings"].append(VL_WARNING)
        result["vl_blocks"] = vl_resp["blocks"]
    result["document"] = document
    if redacted:
        result["warnings"].append(
            f"Đã che số My Number (個人番号) trên {redacted} dòng chữ và trên ảnh: không trích xuất / lưu số này (番号法)."
        )
    if detection is not None:
        result["document_detection"] = detection.to_dict()
        if detection.guessed:
            result["warnings"].append(
                f"Không thấy tiêu đề / nhãn đủ chắc, loại giấy tờ được đoán theo dấu hiệu yếu (điểm đoán: {detection.guess_scores}); "
                "kiểm tra lại hoặc chọn bằng tay."
            )
        elif document is not None and not detection.confident:
            result["warnings"].append(
                f"Tự nhận diện không chắc chắn (điểm: {detection.scores}); kiểm tra lại loại giấy tờ hoặc chọn bằng tay."
            )

    result["ocr"] = {
        "engine": engine,
        "model": model,
        "card_cropped": cropped,
        "deskew_deg": round(deskew, 1),
        "original_size": list(original_size),
        "image_size": [w, h],
        "lines": [{"text": b.text, "score": round(b.score, 4), "box": [round(v, 1) for v in b.box]} for b in boxes],
    }
    result["timing_ms"] = {
        "preprocess": round((t1 - t0) * 1000),
        "ocr": round((t2 - t1) * 1000),
        "parse": round((t3 - t2) * 1000),
    }
    return result, img


def _redact(boxes, img: np.ndarray, vl_resp: dict | None, every_number: bool):
    """Mask My Number in the OCR lines, black out those lines on the returned image, mask the VL blocks."""
    boxes, changed = redact_my_number(boxes, every_number)
    if changed:
        img = img.copy()
        h, w = img.shape[:2]
        for b in changed:
            x1, y1, x2, y2 = (int(round(v)) for v in b.box)
            img[max(y1, 0):min(y2, h), max(x1, 0):min(x2, w)] = 0
    if vl_resp is not None:
        for block in vl_resp["blocks"]:
            if every_number or MY_NUMBER_LABEL_RE.search(block["content"]):
                block["content"] = redact_text(block["content"])
    return boxes, img, vl_resp, len(changed)


def _ocr_text_only(boxes, page_size=None, cropped=False, mode="label") -> dict:
    """document=auto that matched nothing: the same result shape as the parsers, without fields."""
    return build_result(None, {}, Document(drop_non_text(boxes), jp_normalize), {}, "label", [UNKNOWN_WARNING])


def _ocr(img: np.ndarray, engine: str, lang: str):
    """(boxes, image the boxes refer to, deskew angle, model name, VL response or None)."""
    if engine == "vl":
        boxes, vl_resp = vl_client.run_vl(img)
        return boxes, img, 0.0, vl_resp["model"], vl_resp
    boxes, img, deskew = run_ocr(img, lang)
    return boxes, img, deskew, model_name(lang), None
