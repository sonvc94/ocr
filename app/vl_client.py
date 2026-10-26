"""Client for the PaddleOCR-VL service (vl_service/), turning its text blocks into OcrBox lines.

PaddleOCR-VL returns text per layout block with a bbox but no per-line box or confidence, so each
block is split into lines that share the block's height evenly, and every line gets score 1.0.
"""

from __future__ import annotations

import http.client
import json
import os
import urllib.error
import urllib.request
import uuid

from .preprocess import encode_jpeg
from .residence_card import OcrBox

VL_URL = os.getenv("VL_URL", "http://localhost:8011")
VL_MODE = os.getenv("VL_MODE", "layout")
TIMEOUT_S = float(os.getenv("VL_TIMEOUT_S", "600"))


class VlUnavailable(RuntimeError):
    pass


def _post_image(jpeg: bytes, mode: str) -> dict:
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"card.jpg\"\r\n"
        "Content-Type: image/jpeg\r\n\r\n"
    ).encode() + jpeg + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{VL_URL}/ocr?mode={mode}", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return json.load(resp)
    # RemoteDisconnected etc. (service crashed or restarting mid-request) are not URLErrors
    except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError) as exc:
        raise VlUnavailable(f"Không gọi được PaddleOCR-VL ({VL_URL}): {exc}") from exc


def blocks_to_boxes(blocks: list[dict], image_size: tuple[int, int]) -> list[OcrBox]:
    width, _ = image_size
    boxes: list[OcrBox] = []
    y_next = 0.0
    for block in blocks:
        lines = [s.strip() for s in block["content"].splitlines() if s.strip()]
        if not lines:
            continue
        if block.get("bbox"):
            x1, y1, x2, y2 = block["bbox"]
        else:  # whole-image mode: no geometry, stack the lines top to bottom
            x1, y1, x2, y2 = 0.0, y_next, float(width), y_next + 40.0 * len(lines)
        step = (y2 - y1) / len(lines)
        for i, text in enumerate(lines):
            boxes.append(OcrBox(text=text, score=1.0, box=(x1, y1 + i * step, x2, y1 + (i + 1) * step)))
        y_next = y2 + 10
    return boxes


def run_vl(img, mode: str | None = None) -> tuple[list[OcrBox], dict]:
    """Return the OCR lines and the raw service response (blocks, timing)."""
    h, w = img.shape[:2]
    resp = _post_image(encode_jpeg(img, quality=95), mode or VL_MODE)
    return blocks_to_boxes(resp["blocks"], (w, h)), resp
