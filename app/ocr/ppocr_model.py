"""The shared PP-OCR pipeline instances, one per card language, each guarded by its own lock.

Imports nothing from the app: the Dockerfile copies only this module into the layer that downloads
the model weights, so editing other code does not invalidate that (multi-GB) cached layer.
"""

from __future__ import annotations

import os
import threading

# "server" is more accurate on kanji; "mobile" is several times faster on CPU.
MODEL_SIZE = os.getenv("OCR_MODEL_SIZE", "server")
# "gpu:0" | "cpu"; unset = Paddle's default (the GPU when paddlepaddle-gpu sees one, else the CPU).
DEVICE = os.getenv("OCR_DEVICE") or None

# (detection, recognition) per language. Only Japanese documents are read now; the per-language structure
# is kept so another language can be added with its own models.
MODELS = {
    "ja": (f"PP-OCRv5_{MODEL_SIZE}_det", f"PP-OCRv5_{MODEL_SIZE}_rec"),
}

_locks = {lang: threading.Lock() for lang in MODELS}
_ocr: dict = {}


def model_name(lang: str) -> str:
    det, rec = MODELS[lang]
    return f"{det} + {rec}"


def _create(lang: str):
    from paddleocr import PaddleOCR

    det, rec = MODELS[lang]
    return PaddleOCR(
        text_detection_model_name=det,
        text_recognition_model_name=rec,
        use_doc_orientation_classify=True,  # old scans are often rotated 90/180°
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=os.getenv("OCR_ENABLE_MKLDNN", "1") == "1",  # CPU only
        device=DEVICE,
    )


def device_name() -> str:
    """The device the models run on, so a deploy can confirm it really uses the GPU."""
    import paddle

    return DEVICE or paddle.device.get_device()


def get_ocr(lang: str = "ja"):
    with _locks[lang]:
        if lang not in _ocr:
            _ocr[lang] = _create(lang)
    return _ocr[lang]


def predict(img, lang: str = "ja") -> list:
    ocr = get_ocr(lang)
    with _locks[lang]:  # PaddleOCR predictors are not thread-safe
        return list(ocr.predict(img))
