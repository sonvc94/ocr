"""Response shapes of the public API, for the OpenAPI docs (/docs, /redoc, /openapi.json) only.

The endpoints return the pipeline's dicts as they are; these models are passed as `responses=` (not `response_model=`),
so they document the output without filtering it. Keep them in step with pipeline.extract and the parsers
(card_core.pattern_card.build_result, residence_card.parser) and docs/API.md.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    value: str | None = Field(description="Giá trị đã làm sạch/chuẩn hoá (ngày dạng ISO `YYYY-MM-DD`); `null` nếu không đọc được "
                                          "hoặc mẫu giấy tờ này không in trường đó.")
    raw: str | None = Field(description="Chữ OCR gốc mà giá trị được lấy ra.")
    confidence: float | None = Field(description="Độ tin cậy OCR (0–1) của đoạn chữ chứa giá trị.")
    needs_review: bool = Field(description="`true` → nên cho người kiểm tra lại (đọc không chắc, đã tự sửa ký tự, "
                                           "không qua kiểm tra chéo, ảnh chất lượng thấp…).")
    notes: list[str] = Field(description="Lý do gắn cờ / ghi chú xử lý (tiếng Việt).")
    source: str = Field(description="`label` (theo nhãn/mẫu chữ), `zone` (theo vị trí), `label+zone` (hai cách cho cùng kết quả).")


class Quality(BaseModel):
    level: str = Field(description="`ok` hoặc `low` (ảnh mờ/nhỏ/lóa: kết quả không đáng tin, các trường bị gắn `needs_review`).")
    reasons: list[str]
    advice: str | None


class DocumentDetection(BaseModel):
    requested: str = Field(description="Luôn là `auto`.")
    detected: str | None = Field(description="Loại giấy tờ đã chọn (khoá như tham số `document`); `null` = không nhận ra, không đoán được.")
    confident: bool = Field(description="`false` khi loại thứ hai gần điểm, hoặc khi chỉ là đoán.")
    guessed: bool = Field(description="`true` khi không thấy tiêu đề/nhãn đủ chắc, loại được đoán theo dạng số in trên giấy tờ.")
    scores: dict[str, int] = Field(description="Điểm tiêu đề/nhãn của từng loại.")
    guess_scores: dict[str, int] | None = Field(description="Điểm dùng để đoán (chỉ có khi không loại nào đủ điểm).")


class OcrLine(BaseModel):
    text: str
    score: float = Field(description="Độ tin cậy OCR của dòng (0–1).")
    box: list[float] = Field(description="`[x1, y1, x2, y2]` theo pixel trên ảnh đã xử lý (`ocr.image_size`).")


class OcrInfo(BaseModel):
    engine: str
    model: str
    card_cropped: bool = Field(description="Đã tìm thấy viền thẻ, cắt và nắn phẳng.")
    deskew_deg: float = Field(description="Góc đã nắn thẳng (độ).")
    original_size: list[int] = Field(description="`[rộng, cao]` của ảnh gửi lên (sau xoay EXIF).")
    image_size: list[int] = Field(description="`[rộng, cao]` của ảnh đã xử lý mà `lines[].box` tham chiếu.")
    lines: list[OcrLine]


class ExtractResponse(BaseModel):
    request_id: str = Field(description="Mã request (12 ký tự), có trong log server; gửi kèm khi báo lỗi.")
    document: str | None = Field(description="Loại giấy tờ đã đọc (`jp_residence`, `jp_mynumber`, `jp_driver_license`, `jp_passport`, "
                                             "`jp_health_insurance`); `null` khi `document=auto` không nhận ra.")
    document_type: str | None = Field(description="Tên kiểu kết quả: `residence_card`, `my_number_card`, `driver_license`, `passport`, "
                                                  "`health_insurance_card`; `null` khi không nhận ra.")
    side: str = Field(description="Luôn là `front` (chỉ đọc mặt trước).")
    card_design: str | None = Field(description="Thẻ cư trú: mẫu thẻ `2012` / `2026` / `specified_2026`; loại khác `null`.")
    fields: dict[str, ExtractedField] = Field(description="Các trường theo loại giấy tờ (xem mô tả endpoint). `{}` khi không nhận ra giấy tờ.")
    quality: Quality
    warnings: list[str] = Field(description="Cảnh báo cho cả kết quả (tiếng Việt), vd nhận diện không chắc, thẻ hết hạn.")
    mean_ocr_confidence: float | None
    labels_found: list[str]
    labels_from_english_anchor: list[str]
    layout: dict = Field(description="Chỉ có ý nghĩa với `mode=zone|hybrid` (thẻ cư trú): `mode`, `registration`, `zones_px`.")
    full_text: str = Field(description="Toàn bộ chữ OCR đã gom theo dòng (`\\n` giữa các dòng).")
    document_detection: DocumentDetection | None = Field(None, description="Chỉ có khi `document=auto`.")
    ocr: OcrInfo
    timing_ms: dict[str, int] = Field(description="Thời gian xử lý: `preprocess`, `ocr`, `parse` (ms).")
    processed_image: str | None = Field(None, description="Ảnh đã xử lý dạng `data:image/jpeg;base64,…`, chỉ khi `include_image=true`.")


class ErrorResponse(BaseModel):
    detail: str | list = Field(description="Thông báo lỗi (tiếng Việt), hoặc danh sách lỗi tham số (422 do FastAPI kiểm tra).")


class HealthResponse(BaseModel):
    status: str = Field(description="`ok` khi service sẵn sàng (model đã nạp).")
    models: dict[str, str] = Field(description="Model OCR theo ngôn ngữ.")
    device: str = Field(description="`cpu` hoặc `gpu:0`.")
    vl_url: str
