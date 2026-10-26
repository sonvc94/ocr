"""PaddleOCR-VL as a small HTTP service: POST an image, get the recognized text blocks back.

Runs in its own container because PaddleOCR-VL needs PaddlePaddle 3.3.x, which breaks PP-OCRv5
on CPU in the main app. Images are processed in memory only.
"""

from __future__ import annotations

import io
import os
import threading
import time
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

PIPELINE_VERSION = os.getenv("VL_PIPELINE_VERSION", "v1.5")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_lock = threading.Lock()
_vl = None


def get_vl():
    global _vl
    with _lock:
        if _vl is None:
            from paddleocr import PaddleOCRVL

            _vl = PaddleOCRVL(
                pipeline_version=PIPELINE_VERSION,
                use_doc_orientation_classify=False,  # the main app already rotates and crops the card
                use_doc_unwarping=False,
            )
    return _vl


def _block_dict(b) -> dict:
    get = b.get if isinstance(b, dict) else lambda k, d=None: getattr(b, k, d)
    label = get("block_label") or get("label")
    bbox = get("block_bbox") or get("bbox")
    content = get("block_content") or get("content") or ""
    return {
        "label": label,
        "bbox": None if bbox is None else [round(float(v), 1) for v in list(bbox)[:4]],
        "content": str(content),
    }


def run_vl(img: np.ndarray, mode: str) -> list[dict]:
    kwargs = {} if mode == "layout" else {"use_layout_detection": False, "prompt_label": "ocr"}
    vl = get_vl()
    with _lock:  # predictors are not thread-safe
        results = list(vl.predict(img, **kwargs))
    blocks = []
    for res in results:
        blocks += [_block_dict(b) for b in res["parsing_res_list"]]
    return blocks


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_vl()  # load at startup so the first request is not slow
    yield


app = FastAPI(title="PaddleOCR-VL service", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "model": f"PaddleOCR-VL-{PIPELINE_VERSION}"}


@app.post("/ocr")
def ocr(file: UploadFile = File(...), mode: str = Query("layout", pattern="^(layout|whole)$")):
    """mode=layout: layout detection first, one block per detected region (with bbox).
    mode=whole: the whole image is read as one block of text (no bbox)."""
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image larger than 10MB.")
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(415, "Cannot decode image.")
    arr = np.asarray(img)[:, :, ::-1].copy()  # RGB -> BGR, as Paddle expects
    t0 = time.perf_counter()
    blocks = run_vl(arr, mode)
    return {
        "model": f"PaddleOCR-VL-{PIPELINE_VERSION}",
        "mode": mode,
        "image_size": list(img.size),
        "blocks": blocks,
        "timing_ms": round((time.perf_counter() - t0) * 1000),
    }
