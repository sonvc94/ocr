# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quy tắc bắt buộc

- **Mọi thay đổi về logic** (luồng xử lý, parser, rule trích xuất, kiểm tra chéo, ngưỡng chất lượng, API/tham số,
  biến môi trường, cách deploy) **phải được cập nhật vào file này** (mục "Kiến trúc & logic" bên dưới) trong cùng lần
  thay đổi, để các session sau hiểu project mà không cần đọc lại toàn bộ code.
- Nếu thay đổi ảnh hưởng tới người dùng (cách chạy, API, trường trả về, log) thì cập nhật cả `README.md`.
- Ghi ngắn gọn: cái gì, ở đâu (file/hàm), và **vì sao** (nhất là các quyết định không hiển nhiên, workaround, version pin).
- Xoá/sửa nội dung đã lỗi thời thay vì chỉ thêm vào.
- Mọi file sinh ra khi chạy/test đều lưu **trong project**, không dùng thư mục tạm (scratchpad, /tmp):
  log service → `logs/`, kết quả test/JSON trả về từ API → `samples/results/<tên ảnh>.<engine>.json`.

## Tổng quan

Demo OCR mặt trước thẻ cư trú Nhật (在留カード): upload ảnh → JSON các trường. Chạy hoàn toàn local.

```
Upload → preprocess (EXIF rotate, tìm viền thẻ, cắt + nắn phẳng)
       → OCR (engine=ppocr: PP-OCRv5 | engine=vl: PaddleOCR-VL qua vl_service)
       → parse_residence_card (theo nhãn) → kiểm tra chéo + đánh giá chất lượng → JSON
```

## Lệnh thường dùng

Compose chỉ mount `samples/` và `logs/`; code `app/`, `tests/`, `scripts/` được COPY vào image → **sửa code xong phải
`--build`** (hoặc mount thêm `-v ./app:/app/app -v ./tests:/app/tests`), nếu không sẽ chạy/test code cũ.

```bash
docker compose up -d --build                       # app ở http://localhost:8000
docker compose logs -f app
docker compose run --rm app python -m pytest -q tests                                   # toàn bộ test
docker compose run --rm -v ./app:/app/app -v ./tests:/app/tests app \
  python -m pytest -q tests/test_residence_card.py -k <tên_test>                       # 1 test, code hiện tại
curl -s -F file=@samples/isa/residence_card_new_2026.jpg \
  "localhost:8000/api/extract?include_image=false&engine=ppocr" \
  > samples/results/residence_card_new_2026.ppocr.json                                 # engine=vl cần vl_service chạy
docker compose run --rm -v ./app/static:/app/app/static app python -m scripts.build_demo  # cập nhật static/samples
```

Không có linter/formatter cấu hình sẵn.

Biến môi trường: `OCR_MODEL_SIZE`, `OCR_ENABLE_MKLDNN` (mặc định 1), `LOG_RESPONSES`, `LOG_FILE`, `DEBUG_SAVE_IMAGES`
(code mặc định 0, compose bật 1), `VL_URL`, `VL_MODE=layout|whole`, `VL_TIMEOUT_S` (600); vl_service:
`VL_PIPELINE_VERSION` (mặc định `v1.5`).

## Kiến trúc & logic

### app/ (FastAPI, Docker linux/amd64, cổng 8000)
- `main.py`: `/`, `/api/health`, `POST /api/extract?crop=&include_image=&engine=ppocr|vl`. Giới hạn 10MB.
  Log 1 dòng tóm tắt/request (không có PII). `LOG_RESPONSES=1` → ghi full kết quả vào `logs/extract.jsonl`;
  `DEBUG_SAVE_IMAGES=1` → lưu ảnh gốc + ảnh đã xử lý vào `logs/images/`. Cả hai chứa PII, compose đang bật mặc định.
- `preprocess.py`: OpenCV tìm 4 góc thẻ (`find_card`) và warp (`normalize_card`).
- `ocr_engine.py`: PP-OCRv5, `OCR_MODEL_SIZE=server|mobile`, có phân loại hướng 0/90/180/270.
- `residence_card.py`: lõi parser.
  - Gom box thành dòng → tìm nhãn JP (氏名, 生年月日, 住居地, 在留資格…) → cắt giá trị 15 trường.
  - Fallback: nhãn tiếng Anh (`NAME`, `DATE OF BIRTH`, `ADDRESS`…) → liệt kê ở `labels_from_english_anchor`,
    luôn `needs_review`.
  - Sửa ký tự số thẻ, chuẩn hoá ngày, `_cross_check` (ngày sinh < ngày cấp, hết hạn ≥ ngày cấp…).
  - `_card_design` nhận 3 mẫu thẻ: `2012`, `2026` (từ 14/06/2026 không in period_of_stay, permission_type,
    issuing_authority, permission_date, issue_date — chỉ lưu trong chip IC → trả `null`, `needs_review=false`),
    `specified_2026` (特定在留カード gộp My Number, chưa hỗ trợ → mọi trường `needs_review`).
  - `_assess_quality`: `low` khi conf TB < 0.9, > 20% dòng conf < 0.8, hoặc < 60% nhãn JP đọc được.
  - `needs_review` khi: không đọc được, conf < 0.85, đã tự sửa, fail kiểm tra chéo, hoặc quality `low` (trường kanji).
- `vl_client.py`: gọi `VL_URL` (mặc định `host.docker.internal:8011`), tách block thành dòng `OcrBox`, score = 1.0
  (VL không trả confidence).
- `static/`: UI HTML/JS thuần.

### vl_service/ (PaddleOCR-VL, cổng 8011)
- Tách riêng vì VL cần paddlepaddle 3.3.x, bản này crash PP-OCRv5 trên CPU (oneDNN). App chính pin 3.2.2.
- **Quyết định: chạy native trên host, không đưa vào Docker** (dù có `vl_service/Dockerfile`). Lý do: máy dev là Mac M4
  16GB, container phải chạy amd64 qua Rosetta (chậm hơn), và VL trên CPU nạp weight float32 cần > 8GB RAM cho Docker.
  Chạy (Python 3.10, `.venv` có sẵn), log luôn ghi vào `logs/vl_service.log` trong project (không để ở thư mục tạm):
  `cd vl_service && .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8011 >> ../logs/vl_service.log 2>&1`
- Mode `layout` (block có bbox) hoặc `whole` (không bbox).

### scripts/, tests/
- `make_sample.py` sinh thẻ giả; `build_demo.py` tạo kết quả mẫu cho `static/samples`; `download_models.py` tải model khi build.
- `vl_probe.py <ảnh> <pipeline_version>`: dev-only, in format/tốc độ output PaddleOCR-VL (cần venv của vl_service).
- Test parser dùng OCR fixture (`tests/fixtures/*.json`) hoặc box viết tay, không cần Paddle; `test_vl_client.py`
  dựng HTTP server giả thay cho vl_service.
