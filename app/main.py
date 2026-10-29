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
from .api_schema import ErrorResponse, ExtractResponse, HealthResponse
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


API_DESCRIPTION = """
OCR mặt trước giấy tờ Nhật: gửi 1 ảnh, nhận các trường đã trích xuất dạng JSON.

| `document` | Giấy tờ | Trường trả về (`fields`) |
|---|---|---|
| `jp_residence` | 在留カード thẻ cư trú | `card_number` |
| `jp_mynumber` | マイナンバーカード | `issuer`, `expiry_date` |
| `jp_driver_license` | 運転免許証 bằng lái | `license_number`, `issue_date` |
| `jp_passport` | 旅券 hộ chiếu Nhật | `passport_number` |
| `jp_health_insurance` | 健康保険証 / 資格確認書 | `card_type`, `insurer_name`, `issue_date` |
| `auto` | tự nhận diện | theo loại nhận ra; không nhận ra → `fields: {}` + chữ OCR (không lỗi) |

Hướng dẫn tích hợp đầy đủ (ví dụ curl / Python / JavaScript, cách đọc kết quả, mã lỗi): tab **API** trên trang chủ.
"""

app = FastAPI(
    title="OCR giấy tờ Nhật",
    version="1.0",
    description=API_DESCRIPTION,
    lifespan=lifespan,
    openapi_tags=[{"name": "OCR", "description": "Trích xuất trường từ ảnh giấy tờ."},
                  {"name": "Hệ thống", "description": "Trạng thái service, template toạ độ."}],
)
app.mount("/static", RevalidatedStaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    # Version asset URLs by mtime so copies cached before an update (browser or proxy) are bypassed.
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for name in ("app.js", "docs.js", "style.css"):
        version = int((STATIC_DIR / name).stat().st_mtime)
        html = html.replace(f"/static/{name}\"", f"/static/{name}?v={version}\"")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/api/zones", tags=["Hệ thống"], summary="Template toạ độ của mẫu thẻ")
def zones(document: str = Query("jp_residence", pattern=f"^({'|'.join(pipeline.DOCUMENTS)})$")):
    """Card templates (label/value positions) used by mode=zone/hybrid; drawn in the "Giấy tờ hỗ trợ" tab."""
    return JP_TEMPLATES if document == "jp_residence" else {}  # pattern-only documents: no template


@app.get("/api/health", tags=["Hệ thống"], summary="Trạng thái service", response_model=HealthResponse)
def health():
    """`status: ok` khi model đã nạp xong và sẵn sàng nhận request; `device` là `cpu` hoặc `gpu:0`."""
    return {
        "status": "ok",
        "models": {lang: ppocr_model.model_name(lang) for lang in ppocr_model.MODELS},
        "device": ppocr_model.device_name(),
        "vl_url": config.VL_URL,
    }


@app.post(
    "/api/extract",
    tags=["OCR"],
    summary="Trích xuất trường từ ảnh giấy tờ",
    responses={
        200: {"model": ExtractResponse, "description": "Kết quả (kể cả khi `document=auto` không nhận ra giấy tờ: `fields: {}`)."},
        413: {"model": ErrorResponse, "description": "Ảnh lớn hơn 10MB."},
        415: {"model": ErrorResponse, "description": "File không phải ảnh JPEG / PNG / WEBP đọc được."},
        422: {"model": ErrorResponse, "description": "Tham số sai (giá trị không hợp lệ, thiếu `file`, `engine=vl` với `mode≠label`)."},
        503: {"model": ErrorResponse, "description": "`engine=vl` mà dịch vụ PaddleOCR-VL không chạy."},
    },
)
def extract(
    file: UploadFile = File(..., description="Ảnh giấy tờ (JPEG / PNG / WEBP, tối đa 10MB), gửi dạng `multipart/form-data`."),
    crop: bool = Query(True, description="Tự tìm viền thẻ, cắt và nắn phẳng (hộ chiếu không cắt)."),
    include_image: bool = Query(True, description="Trả kèm ảnh đã xử lý (base64, vài trăm KB). Tích hợp hệ thống nên đặt `false`."),
    engine: str = Query("ppocr", pattern=f"^({'|'.join(pipeline.ENGINES)})$",
                        description="`ppocr` (PP-OCRv5, mặc định) hoặc `vl` (PaddleOCR-VL, cần dịch vụ VL chạy riêng, chậm hơn nhiều)."),
    mode: str = Query("label", pattern=f"^({'|'.join(pipeline.MODES)})$",
                      description="`label` (theo nhãn in sẵn, mặc định), `zone` (theo vị trí trên mẫu thẻ), `hybrid` (cả hai). "
                                  "`zone`/`hybrid` chỉ có tác dụng với thẻ cư trú."),
    document: str = Query("jp_residence", pattern=f"^({'|'.join(pipeline.DOCUMENT_CHOICES)})$",
                          description="Loại giấy tờ, hoặc `auto` để tự nhận diện. Mặc định `jp_residence` (giữ tương thích client cũ)."),
):
    """Gửi 1 ảnh mặt trước giấy tờ, nhận `fields` (mỗi trường có `value`, `confidence`, `needs_review`…).

    Nên kiểm tra `needs_review` của từng trường và `warnings`: `true` nghĩa là giá trị có thể sai, cần người xem lại.
    Xử lý đồng bộ, khoảng 0.5–1 giây/ảnh trên GPU (vài giây trên CPU); các request được OCR lần lượt.
    """
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
