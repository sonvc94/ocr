"""Instantiate the OCR pipelines once at build time so the models are baked into the image."""

from app.ocr.ppocr_model import MODELS, get_ocr

for lang in MODELS:
    get_ocr(lang)
print("models ready")
