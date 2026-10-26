"""OCR engines. Each returns a list of `types.OcrBox` lines for the residence-card parser.

Kept import-free on purpose: the Dockerfile copies only this file and `ppocr_model.py` into the
model-download layer.
"""
