# 在留カード OCR demo

Website demo: upload ảnh **mặt trước thẻ cư trú Nhật (在留カード)** → trích xuất thông tin ra JSON.
OCR bằng PaddleOCR (PP-OCRv5), trích xuất trường bằng rule. Chạy hoàn toàn local, ảnh chỉ xử lý trong bộ nhớ.

## Chạy

```bash
docker compose up -d --build     # lần đầu ~5 phút (tải Paddle + model)
open http://localhost:8000
```

Đổi sang model nhẹ hơn (nhanh gấp ~4–5 lần, kém chính xác hơn):

```bash
OCR_MODEL_SIZE=mobile docker compose up -d
```

> PaddlePaddle không có wheel Linux ARM64, nên trên Mac Apple Silicon container chạy `linux/amd64` qua Rosetta
> (Docker Desktop → Settings → General → bật *Use Rosetta for x86_64/amd64 emulation*).
> Nếu cần nhanh hơn, có thể chạy native trên macOS với Python 3.10–3.13: `pip install -r requirements.txt && uvicorn app.main:app`.

## API

```bash
curl -F file=@samples/synthetic_photo.jpg "localhost:8000/api/extract?include_image=false"
```

| Query param | Mặc định | Ý nghĩa |
|---|---|---|
| `crop` | `true` | Tự tìm viền thẻ, cắt và nắn phẳng (kể cả thẻ nhạt màu, trong bao nhựa, bị che 1 góc) |
| `include_image` | `true` | Trả kèm ảnh đã xử lý (base64) để hiển thị |

Mỗi trường trả về dạng:

```json
"date_of_birth": { "value": "1995-04-12", "raw": "1995年04月12日", "confidence": 0.9997, "needs_review": false, "notes": [] }
```

Các trường: `card_number, name, date_of_birth, sex, nationality, address, status_of_residence, work_restriction,
period_of_stay, expiration_date, permission_type, issuing_authority, permission_date, issue_date, valid_until`.

`ocr.card_cropped` cho biết đã tìm được viền thẻ để cắt hay chưa; `ocr.deskew_deg` là góc nghiêng (độ) đã được nắn
thẳng dựa trên hướng các dòng chữ khi ảnh còn nghiêng (thường là ảnh không tìm được viền thẻ; chỉ engine `ppocr`), 0 nếu không nắn.

`needs_review = true` khi: không đọc được, độ tin cậy OCR < 0.85, đã tự sửa ký tự, hoặc không qua kiểm tra chéo
(ngày sinh < ngày cấp, hết hạn ≥ ngày cấp…).

## Cấu trúc

```
app/
  main.py            FastAPI: /, /api/health, /api/extract
  preprocess.py      EXIF rotate, tìm & nắn thẻ (OpenCV)
  ocr_engine.py      PaddleOCR PP-OCRv5 (+ phân loại hướng ảnh 0/90/180/270, nắn ảnh nghiêng ≤ 30°)
  residence_card.py  Parser theo nhãn: 氏名, 生年月日, 住居地, 在留資格... + validate
  static/            Giao diện (HTML/JS thuần)
scripts/make_sample.py   Sinh ảnh thẻ giả lập (dữ liệu giả) để test
tests/                   Test parser + tìm viền/nắn nghiêng (không cần Paddle)
```

Test: `docker compose run --rm app python -m pytest -q tests`

## Log

- `docker compose logs -f app`: mỗi request in 1 dòng tóm tắt `extract id=... found=.. missing=[..] review=[..] labels=[..]`
  (không có dữ liệu cá nhân).
- `logs/extract.jsonl`: khi `LOG_RESPONSES=1` (mặc định trong compose), ghi toàn bộ kết quả mỗi request (trường, dòng OCR
  thô, full text, không kèm ảnh). **File này chứa thông tin cá nhân trên thẻ**: tắt bằng `LOG_RESPONSES=0 docker compose up -d`
  và xoá file khi không cần nữa.
- `logs/images/<request_id>_original.*` và `_processed.jpg`: khi `DEBUG_SAVE_IMAGES=1` (mặc định trong compose), lưu ảnh
  upload và ảnh sau khi cắt/nắn để debug. **Cũng là dữ liệu cá nhân**, tắt bằng `DEBUG_SAVE_IMAGES=0`.

## Ảnh chất lượng thấp

- Response có `quality.level` (`ok`/`low`) kèm lý do: độ tin cậy OCR trung bình < 0.9, > 20% dòng có độ tin cậy < 0.8,
  hoặc nhận ra < 60% nhãn tiếng Nhật. Khi `low`, các trường chữ kanji luôn bị đánh dấu `needs_review`, UI hiện banner đỏ.
- Khi nhãn tiếng Nhật đọc lỗi, parser lấy vị trí từ nhãn tiếng Anh in bên dưới (`NAME`, `DATE OF BIRTH`, `ADDRESS`…),
  được liệt kê ở `labels_from_english_anchor`. Ngày cấp phép/cấp thẻ, hạn chế làm việc, loại giấy phép có thêm cách đoán theo mẫu chữ.
  Các trường lấy theo cách này luôn có ghi chú và `needs_review = true`.

## Ghi chú

- `paddlepaddle` pin ở 3.2.2: bản 3.3.x crash trên CPU khi bật oneDNN (`ConvertPirAttribute2RuntimeAttribute not support`).
- Ảnh trong `samples/` là thẻ **giả lập** với dữ liệu giả, layout chỉ gần giống thẻ thật. Độ chính xác trên ảnh thật cần đo lại.
