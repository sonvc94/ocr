"""The shared PP-OCRv5 pipeline instance. One instance, guarded by a lock.

Imports nothing from the app: the Dockerfile copies only this module into the layer that downloads
the model weights, so editing other code does not invalidate that (multi-GB) cached layer.
"""

from __future__ import annotations

import os
import threading

# "server" is more accurate on kanji; "mobile" is several times faster on CPU.
MODEL_SIZE = os.getenv("OCR_MODEL_SIZE", "server")
MODEL_NAME = f"PP-OCRv5_{MODEL_SIZE}"

_lock = threading.Lock()
_ocr = None


def _create():
    from paddleocr import PaddleOCR

    return PaddleOCR(
        text_detection_model_name=f"{MODEL_NAME}_det",
        text_recognition_model_name=f"{MODEL_NAME}_rec",
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


def predict(img) -> list:
    ocr = get_ocr()
    with _lock:  # PaddleOCR predictors are not thread-safe
        return list(ocr.predict(img))
