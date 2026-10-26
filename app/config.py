"""App settings from environment variables, read once at import.

The PP-OCR model settings (OCR_MODEL_SIZE, OCR_ENABLE_MKLDNN) live in `ocr/ppocr_model.py`, which
must stay free of app imports (see its docstring).
"""

from __future__ import annotations

import os
from pathlib import Path

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# 1 = append full results (personal data from the card) to LOG_FILE.
LOG_RESPONSES = os.getenv("LOG_RESPONSES", "0") == "1"
LOG_FILE = Path(os.getenv("LOG_FILE", "logs/extract.jsonl"))
# 1 = save every uploaded and processed image (personal data!) next to the log so failures can be inspected.
DEBUG_SAVE_IMAGES = os.getenv("DEBUG_SAVE_IMAGES", "0") == "1"
IMAGE_DIR = LOG_FILE.parent / "images"

# PaddleOCR-VL service (vl_service/), used when /api/extract is called with engine=vl.
VL_URL = os.getenv("VL_URL", "http://localhost:8011")
VL_MODE = os.getenv("VL_MODE", "layout")  # layout | whole
VL_TIMEOUT_S = float(os.getenv("VL_TIMEOUT_S", "600"))
