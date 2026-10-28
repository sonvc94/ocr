"""The full extraction: image → (crop + flatten) → OCR → parse → result dict. Shared by the API and scripts."""

from __future__ import annotations

import time
from functools import partial

import numpy as np

from .detect import detect_document
from .driver_license import parse_driver_license
from .health_insurance import parse_health_insurance
from .my_number_card import parse_my_number_card
from .passport import parse_passport
from .ocr import vl_client
from .ocr.ppocr import run_ocr
from .ocr.ppocr_model import model_name
from .preprocess import normalize_card
from .residence_card import MODES, parse_residence_card

ENGINES = ("ppocr", "vl")
# document type -> (parser, OCR language, crop the ID-1 card). Cards share the crop/flatten step; the passport
# photo page is not ID-1 and is usually photographed open (2 pages ≈ same aspect as 1 page), so it is not cropped.
DOCUMENTS = {
    # the user needs only the card number of the residence card (other fields still parsed internally)
    "jp_residence": (partial(parse_residence_card, keys=("card_number",)), "ja", True),
    "jp_mynumber": (parse_my_number_card, "ja", True),
    "jp_driver_license": (parse_driver_license, "ja", True),
    "jp_passport": (parse_passport, "ja", False),
    "jp_health_insurance": (parse_health_insurance, "ja", True),
}

# document=auto: crop as an ID-1 card, OCR, then detect.py picks the document (all use the "ja" OCR).
AUTO = "auto"
DOCUMENT_CHOICES = (AUTO, *DOCUMENTS)


class UnknownDocument(ValueError):
    """document=auto and no document's printed words were found."""

    def __init__(self, scores: dict[str, int]):
        super().__init__(
            "Không nhận ra loại giấy tờ (không thấy tiêu đề / nhãn của loại nào). Hãy chụp rõ hơn hoặc chọn loại giấy tờ bằng tay."
        )
        self.scores = scores


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

    document="auto" detects the document from the OCR text (detect.py) and adds `document_detection` to the result;
    raises UnknownDocument when nothing matches. Every result carries the `document` that was parsed.

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
        if detection.document is None:
            raise UnknownDocument(detection.scores)
        document = detection.document
        if cropped and not DOCUMENTS[document][2]:  # passport: read the uncropped image like document=jp_passport
            img, cropped = original, False
            boxes, img, deskew, model, vl_resp = _ocr(img, engine, lang)
    parse = DOCUMENTS[document][0]
    t2 = time.perf_counter()
    h, w = img.shape[:2]
    result = parse(boxes, page_size=(w, h), cropped=cropped, mode=mode)
    t3 = time.perf_counter()
    if vl_resp is not None:
        result["warnings"].append(VL_WARNING)
        result["vl_blocks"] = vl_resp["blocks"]
    result["document"] = document
    if detection is not None:
        result["document_detection"] = detection.to_dict()
        if not detection.confident:
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


def _ocr(img: np.ndarray, engine: str, lang: str):
    """(boxes, image the boxes refer to, deskew angle, model name, VL response or None)."""
    if engine == "vl":
        boxes, vl_resp = vl_client.run_vl(img)
        return boxes, img, 0.0, vl_resp["model"], vl_resp
    boxes, img, deskew = run_ocr(img, lang)
    return boxes, img, deskew, model_name(lang), None
