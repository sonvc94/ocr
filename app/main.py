"""FastAPI app: POST an image of a residence card, get the extracted fields back as JSON.

Uploaded images are processed in memory and never written to disk. When LOG_RESPONSES=1 the
extraction result (which contains the card holder's personal data) is appended to
logs/extract.jsonl for debugging.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import UnidentifiedImageError

from . import ocr_engine, vl_client
from .preprocess import encode_jpeg, load_image, normalize_card
from .residence_card import parse_residence_card

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
STATIC_DIR = Path(__file__).parent / "static"
LOG_RESPONSES = os.getenv("LOG_RESPONSES", "0") == "1"
LOG_FILE = Path(os.getenv("LOG_FILE", "logs/extract.jsonl"))
# Saves every uploaded image (personal data!) next to the log so failures can be inspected.
DEBUG_SAVE_IMAGES = os.getenv("DEBUG_SAVE_IMAGES", "0") == "1"
IMAGE_DIR = LOG_FILE.parent / "images"

logger = logging.getLogger("uvicorn.error")
_log_lock = threading.Lock()


def log_result(request_id: str, filename: str | None, result: dict) -> None:
    fields = result["fields"]
    missing = [k for k, f in fields.items() if f["value"] is None]
    review = [k for k, f in fields.items() if f["needs_review"] and f["value"] is not None]
    logger.info(
        "extract id=%s model=%s file=%s size=%s quality=%s found=%d/%d missing=%s review=%s anchored=%s timing=%s",
        request_id, result["ocr"]["model"], filename, result["ocr"]["original_size"], result["quality"]["level"],
        len(fields) - len(missing), len(fields), missing, review,
        result["labels_from_english_anchor"], result["timing_ms"],
    )
    if not LOG_RESPONSES:
        return
    entry = {"id": request_id, "time": datetime.now(timezone.utc).isoformat(), "filename": filename}
    entry |= {k: v for k, v in result.items() if k != "processed_image"}
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _log_lock, LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


@asynccontextmanager
async def lifespan(_: FastAPI):
    ocr_engine.get_ocr()  # load models at startup so the first request is not slow
    yield


class RevalidatedStaticFiles(StaticFiles):
    """Makes browsers revalidate (cheap 304 via ETag) so an updated app.js is never served stale."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="Residence Card OCR Demo", lifespan=lifespan)
app.mount("/static", RevalidatedStaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    # Version asset URLs by mtime so copies cached before an update (browser or proxy) are bypassed.
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for name in ("app.js", "style.css"):
        version = int((STATIC_DIR / name).stat().st_mtime)
        html = html.replace(f"/static/{name}\"", f"/static/{name}?v={version}\"")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
def health():
    return {"status": "ok", "model": f"PP-OCRv5_{ocr_engine.MODEL_SIZE}", "vl_url": vl_client.VL_URL}


@app.post("/api/extract")
def extract(
    file: UploadFile = File(...),
    crop: bool = True,
    include_image: bool = True,
    engine: str = Query("ppocr", pattern="^(ppocr|vl)$"),
):
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Ảnh vượt quá 10MB.")
    request_id = uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    try:
        img, original_size = load_image(data)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(415, "Không đọc được file ảnh (hỗ trợ JPEG, PNG, WEBP).")
    if DEBUG_SAVE_IMAGES:
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        suffix = Path(file.filename or "").suffix.lower() or ".img"
        (IMAGE_DIR / f"{request_id}_original{suffix}").write_bytes(data)

    cropped = False
    if crop:
        img, cropped = normalize_card(img)
    t1 = time.perf_counter()
    vl_resp = None
    if engine == "vl":
        try:
            boxes, vl_resp = vl_client.run_vl(img)
        except vl_client.VlUnavailable as exc:
            raise HTTPException(503, str(exc))
        model = vl_resp["model"]
    else:
        boxes, img = ocr_engine.run_ocr(img)
        model = f"PP-OCRv5_{ocr_engine.MODEL_SIZE}"
    t2 = time.perf_counter()
    result = parse_residence_card(boxes)
    t3 = time.perf_counter()
    if vl_resp is not None:
        result["warnings"].append(
            "PaddleOCR-VL không trả độ tin cậy theo dòng: needs_review chỉ dựa vào định dạng và kiểm tra chéo, "
            "đánh giá chất lượng ảnh chỉ dựa vào số nhãn đọc được."
        )
        result["vl_blocks"] = vl_resp["blocks"]

    h, w = img.shape[:2]
    result["ocr"] = {
        "engine": engine,
        "model": model,
        "card_cropped": cropped,
        "original_size": list(original_size),
        "image_size": [w, h],
        "lines": [{"text": b.text, "score": round(b.score, 4), "box": [round(v, 1) for v in b.box]} for b in boxes],
    }
    result["timing_ms"] = {
        "preprocess": round((t1 - t0) * 1000),
        "ocr": round((t2 - t1) * 1000),
        "parse": round((t3 - t2) * 1000),
    }
    result["request_id"] = request_id
    log_result(request_id, file.filename, result)
    processed_jpeg = encode_jpeg(img) if include_image or DEBUG_SAVE_IMAGES else None
    if DEBUG_SAVE_IMAGES:
        (IMAGE_DIR / f"{request_id}_processed.jpg").write_bytes(processed_jpeg)
    if include_image:
        result["processed_image"] = "data:image/jpeg;base64," + base64.b64encode(processed_jpeg).decode()
    return result
