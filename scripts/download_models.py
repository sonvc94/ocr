"""Instantiate the OCR pipeline once at build time so the models are baked into the image."""

from app.ocr.ppocr_model import get_ocr

get_ocr()
print("models ready")
