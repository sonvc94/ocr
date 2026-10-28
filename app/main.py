"""FastAPI app: POST an image of a Japanese document (residence card, My Number card, driver's license, passport,
health insurance card), get the fields back as JSON.

Uploaded images are processed in memory. Logging of personal data (full results, images) is
opt-in, see config.py and request_log.py.
"""

from __future__ import annotations

import base64
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import UnidentifiedImageError

from . import config, pipeline, request_log
from .ocr import ppocr_model, vl_client
from .preprocess import encode_jpeg, load_image
from .residence_card.templates import TEMPLATES as JP_TEMPLATES

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    for lang in ppocr_model.MODELS:
        ppocr_model.get_ocr(lang)  # load models at startup so the first request is not slow
    yield


class RevalidatedStaticFiles(StaticFiles):
    """Makes browsers revalidate (cheap 304 via ETag) so an updated app.js is never served stale."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


app = FastAPI(title="Card OCR Demo", lifespan=lifespan)
app.mount("/static", RevalidatedStaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    # Version asset URLs by mtime so copies cached before an update (browser or proxy) are bypassed.
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for name in ("app.js", "docs.js", "style.css"):
        version = int((STATIC_DIR / name).stat().st_mtime)
        html = html.replace(f"/static/{name}\"", f"/static/{name}?v={version}\"")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/api/zones")
def zones(document: str = Query("jp_residence", pattern=f"^({'|'.join(pipeline.DOCUMENTS)})$")):
    """Card templates (label/value positions) used by mode=zone/hybrid; drawn on static/design.html."""
    return JP_TEMPLATES if document == "jp_residence" else {}  # pattern-only documents: no template


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "models": {lang: ppocr_model.model_name(lang) for lang in ppocr_model.MODELS},
        "device": ppocr_model.device_name(),
        "vl_url": config.VL_URL,
    }


@app.post("/api/extract")
def extract(
    file: UploadFile = File(...),
    crop: bool = True,
    include_image: bool = True,
    engine: str = Query("ppocr", pattern=f"^({'|'.join(pipeline.ENGINES)})$"),
    mode: str = Query("label", pattern=f"^({'|'.join(pipeline.MODES)})$"),
    document: str = Query("jp_residence", pattern=f"^({'|'.join(pipeline.DOCUMENTS)})$"),
):
    if engine == "vl" and mode != "label":
        raise HTTPException(422, "mode=zone/hybrid chỉ hỗ trợ engine=ppocr (VL không trả khung theo từng dòng).")
    data = file.file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Ảnh vượt quá 10MB.")
    request_id = uuid.uuid4().hex[:12]
    try:
        img, original_size = load_image(data)
    except (UnidentifiedImageError, OSError):
        raise HTTPException(415, "Không đọc được file ảnh (hỗ trợ JPEG, PNG, WEBP).")
    request_log.save_image(request_id, "original", data, request_log.upload_suffix(file.filename))

    try:
        result, processed = pipeline.extract(img, original_size, crop=crop, engine=engine, mode=mode, document=document)
    except vl_client.VlUnavailable as exc:
        raise HTTPException(503, str(exc))
    result["request_id"] = request_id
    request_log.log_result(request_id, file.filename, result)

    processed_jpeg = encode_jpeg(processed) if include_image or config.DEBUG_SAVE_IMAGES else None
    if processed_jpeg is not None:
        request_log.save_image(request_id, "processed", processed_jpeg, ".jpg")
    if include_image:
        result["processed_image"] = "data:image/jpeg;base64," + base64.b64encode(processed_jpeg).decode()
    return result
