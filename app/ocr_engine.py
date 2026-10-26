"""Thin wrapper around PaddleOCR (PP-OCRv5). One shared instance, guarded by a lock."""

from __future__ import annotations

import os
import threading

import numpy as np

from .residence_card import OcrBox

# "server" is more accurate on kanji; "mobile" is several times faster on CPU.
MODEL_SIZE = os.getenv("OCR_MODEL_SIZE", "server")

_lock = threading.Lock()
_ocr = None


def _create():
    from paddleocr import PaddleOCR

    return PaddleOCR(
        text_detection_model_name=f"PP-OCRv5_{MODEL_SIZE}_det",
        text_recognition_model_name=f"PP-OCRv5_{MODEL_SIZE}_rec",
        use_doc_orientation_classify=True,  # old scans are often rotated 90/180°
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=os.getenv("OCR_ENABLE_MKLDNN", "1") == "1",
    )


def get_ocr():
    global _ocr
    with _lock:
        if _ocr is None:
            _ocr = _create()
    return _ocr


def run_ocr(img: np.ndarray) -> tuple[list[OcrBox], np.ndarray]:
    """Return the text boxes and the image they refer to (rotated if orientation was corrected)."""
    ocr = get_ocr()
    with _lock:  # PaddleOCR predictors are not thread-safe
        results = ocr.predict(img)
    boxes: list[OcrBox] = []
    used = img
    for res in results:
        doc_pre = res.get("doc_preprocessor_res")
        if doc_pre is not None and doc_pre.get("output_img") is not None:
            used = doc_pre["output_img"]
        for text, score, box in zip(res["rec_texts"], res["rec_scores"], res["rec_boxes"]):
            if text.strip():
                boxes.append(OcrBox(text=text, score=float(score), box=tuple(float(v) for v in box)))
    return boxes, used
