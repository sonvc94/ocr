"""The full extraction: image → (crop + flatten) → OCR → parse → result dict. Shared by the API and scripts."""

from __future__ import annotations

import time

import numpy as np

from .ocr import vl_client
from .ocr.ppocr import run_ocr
from .ocr.ppocr_model import MODEL_NAME
from .preprocess import normalize_card
from .residence_card import parse_residence_card

ENGINES = ("ppocr", "vl")

VL_WARNING = (
    "PaddleOCR-VL không trả độ tin cậy theo dòng: needs_review chỉ dựa vào định dạng và kiểm tra chéo, "
    "đánh giá chất lượng ảnh chỉ dựa vào số nhãn đọc được."
)


def extract(img: np.ndarray, original_size: tuple[int, int], crop: bool = True, engine: str = "ppocr") -> tuple[dict, np.ndarray]:
    """Return the result and the processed image its boxes refer to.

    Raises vl_client.VlUnavailable when engine="vl" and the VL service cannot be reached.
    """
    t0 = time.perf_counter()
    cropped = False
    if crop:
        img, cropped = normalize_card(img)
    t1 = time.perf_counter()
    vl_resp = None
    deskew = 0.0
    if engine == "vl":
        boxes, vl_resp = vl_client.run_vl(img)
        model = vl_resp["model"]
    else:
        boxes, img, deskew = run_ocr(img)
        model = MODEL_NAME
    t2 = time.perf_counter()
    result = parse_residence_card(boxes)
    t3 = time.perf_counter()
    if vl_resp is not None:
        result["warnings"].append(VL_WARNING)
        result["vl_blocks"] = vl_resp["blocks"]

    h, w = img.shape[:2]
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
