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


# Below this tilt the axis-aligned boxes are already good enough; above the max it is not a tilt
# (the 90/180/270° cases are handled by the orientation classifier).
DESKEW_MIN_DEG = 1.0
DESKEW_MAX_DEG = 30.0


def run_ocr(img: np.ndarray) -> tuple[list[OcrBox], np.ndarray, float]:
    """Return the text boxes, the image they refer to (rotated if orientation/tilt was corrected)
    and the tilt in degrees that was straightened (0 if none).

    A tilted photo whose card edge was not found is straightened here: the quads from text
    detection give the tilt, the image is rotated and the quads mapped into it, so each line's
    box is tight and rows group correctly. Recognition itself already reads the tilted quads.
    """
    # Imported here: the Dockerfile copies only this module + residence_card.py into the model-download
    # layer, so a module-level import of preprocess would break that build step.
    from .preprocess import estimate_skew, rotate

    ocr = get_ocr()
    with _lock:  # PaddleOCR predictors are not thread-safe
        results = ocr.predict(img)
    lines: list[tuple[str, float, np.ndarray]] = []
    used = img
    for res in results:
        doc_pre = res.get("doc_preprocessor_res")
        if doc_pre is not None and doc_pre.get("output_img") is not None:
            used = doc_pre["output_img"]
        for text, score, poly in zip(res["rec_texts"], res["rec_scores"], res["rec_polys"]):
            if text.strip():
                lines.append((text, float(score), np.asarray(poly, dtype=np.float32).reshape(-1, 2)))

    skew = estimate_skew([p for _, _, p in lines])
    if DESKEW_MIN_DEG <= abs(skew) <= DESKEW_MAX_DEG:
        used, m = rotate(used, skew)
        lines = [(t, s, p @ m[:, :2].T + m[:, 2]) for t, s, p in lines]
    else:
        skew = 0.0
    boxes = [
        OcrBox(text=t, score=s, box=(float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())))
        for t, s, p in lines
    ]
    return boxes, used, skew
