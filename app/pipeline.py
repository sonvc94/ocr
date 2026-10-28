"""The full extraction: image → (crop + flatten) → OCR → parse → result dict. Shared by the API and scripts."""

from __future__ import annotations

import time
from functools import partial

import numpy as np

from .ocr import vl_client
from .ocr.ppocr import run_ocr
from .ocr.ppocr_model import model_name
from .preprocess import normalize_card
from .driver_license import parse_driver_license
from .health_insurance import parse_health_insurance
from .my_number_card import parse_my_number_card
from .passport import parse_passport
from .residence_card import MODES, parse_residence_card
from .vn_id_card import parse_vn_id_card

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
    "vn_id": (parse_vn_id_card, "vi", True),
}
VL_DOCUMENTS = tuple(d for d in DOCUMENTS if d.startswith("jp_"))  # vl_service runs the Japanese PaddleOCR-VL setup only

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

    mode=zone/hybrid need per-line boxes, which only engine=ppocr gives (VL boxes are whole blocks).
    Raises vl_client.VlUnavailable when engine="vl" and the VL service cannot be reached.
    """
    if engine == "vl" and mode != "label":
        raise ValueError("mode=zone/hybrid chỉ hỗ trợ engine=ppocr.")
    if engine == "vl" and document not in VL_DOCUMENTS:
        raise ValueError("engine=vl chỉ hỗ trợ giấy tờ Nhật.")
    parse, lang, card = DOCUMENTS[document]
    t0 = time.perf_counter()
    cropped = False
    if crop and card:
        img, cropped = normalize_card(img)
    t1 = time.perf_counter()
    vl_resp = None
    deskew = 0.0
    if engine == "vl":
        boxes, vl_resp = vl_client.run_vl(img)
        model = vl_resp["model"]
    else:
        boxes, img, deskew = run_ocr(img, lang)
        model = model_name(lang)
    t2 = time.perf_counter()
    h, w = img.shape[:2]
    result = parse(boxes, page_size=(w, h), cropped=cropped, mode=mode)
    t3 = time.perf_counter()
    if vl_resp is not None:
        result["warnings"].append(VL_WARNING)
        result["vl_blocks"] = vl_resp["blocks"]

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
