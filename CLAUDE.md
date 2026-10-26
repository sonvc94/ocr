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
docker compose run --rm app python -m pytest -q                                         # toàn bộ test
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
Hướng phụ thuộc một chiều: `main` → `pipeline` → (`preprocess`, `ocr/*`, `residence_card/*`); `ocr/types.OcrBox` là
định dạng dòng OCR dùng chung (parser không import engine, engine không import parser).
- `main.py`: chỉ lo HTTP: `/`, `/api/health`, `POST /api/extract?crop=&include_image=&engine=ppocr|vl`. Giới hạn 10MB,
  415 khi không đọc được ảnh, 503 khi engine=vl mà không gọi được vl_service.
- `pipeline.extract(img, original_size, crop, engine)`: cắt/nắn → OCR → parse → gắn `ocr` (engine, model, card_cropped,
  deskew_deg, size, lines) + `timing_ms` (preprocess không tính bước decode ảnh). API và `scripts/build_demo.py` cùng dùng.
- `config.py`: biến môi trường của app (log, VL). Riêng `OCR_MODEL_SIZE`/`OCR_ENABLE_MKLDNN` đọc trong `ocr/ppocr_model.py`.
- `request_log.py`: log 1 dòng tóm tắt/request (không có PII). `LOG_RESPONSES=1` → ghi full kết quả vào `logs/extract.jsonl`;
  `DEBUG_SAVE_IMAGES=1` → lưu ảnh gốc + ảnh đã xử lý vào `logs/images/`. Cả hai chứa PII, compose đang bật mặc định.
- `preprocess.py`: OpenCV tìm 4 góc thẻ (`find_card`) và warp (`normalize_card`). `find_card` có 2 lần quét:
  (1) Canny 50/150 + `RETR_EXTERNAL`, sai lệch tỉ lệ < 0.25; (2) nếu lần 1 không thấy: Canny 20/60 + đóng khe hở
  (morph close 7×7) + `RETR_LIST` + convex hull (bắc qua góc bị ngón tay che), điều kiện chặt hơn (sai lệch tỉ lệ < 0.15,
  2 cạnh đối diện lệch ≤ 15%, diện tích 30–95% ảnh để không cắt nhầm vùng bên trong của ảnh đã cắt sát thẻ), rồi nới rộng
  4% vì hull hay lẹm vào thẻ. Lần 2 thêm vào cho ảnh thẻ nhạt màu trong bao nhựa (log `1.png`, 26/10/2026). Lần 1 giữ nguyên
  để không đổi kết quả các ảnh vốn đã chạy tốt.
- `ocr/ppocr_model.py`: instance PP-OCRv5 dùng chung + lock (predictor không thread-safe), `OCR_MODEL_SIZE=server|mobile`,
  phân loại hướng 0/90/180/270. **Không được import gì từ app**: Dockerfile chỉ copy file này (+ 2 `__init__.py` rỗng)
  vào layer tải model, để sửa code khác không làm mất cache model.
- `ocr/ppocr.py` (`run_ocr`): sau OCR, `estimate_skew` lấy trung vị góc cạnh trên của các polygon chữ (`rec_polys`, chỉ
  box dài > 2× cao, cần ≥ 3 box); nếu 1°–30° thì xoay ảnh (`preprocess.rotate`, canvas nới rộng) và chiếu polygon theo,
  box trả về là bbox của polygon đã thẳng. Không OCR lại (recognition vốn đọc được quad nghiêng). Engine `vl` không có
  polygon → không nắn, chỉ nhờ `group_rows` chịu nghiêng.
- `ocr/vl_client.py`: gọi `VL_URL` (mặc định `host.docker.internal:8011`), tách block thành dòng `OcrBox`, score = 1.0
  (VL không trả confidence). Đọc `config.VL_URL` lúc gọi (test monkeypatch `config`).
- `residence_card/`: lõi parser, API công khai `parse_residence_card`, `group_rows`.
  - `patterns.py`: nhãn JP (`LABELS`), nhãn EN, regex, danh sách giá trị chính thức, bảng ký tự OCR hay nhầm, `normalize`.
  - `layout.py`: `drop_non_text`, `group_rows`, `Document` (text phẳng + map vị trí ký tự → score OCR).
    `group_rows` gom box theo đường có độ dốc, thử dốc −0.18…0.18 (~±10°) và chọn dốc cho ít dòng nhất, nhưng chỉ
    dùng khi ít hơn gom ngang ≥ 2 dòng (để thẻ thẳng không bị ảnh hưởng). Lý do: ảnh nghiêng vài độ làm lệch tâm dọc
    giữa nhãn và giá trị quá nửa chiều cao chữ, nhãn bị tách khỏi giá trị / ghép nhầm sang dòng khác.
  - `fields.py`: `Field` + `extract_fields` (giá trị mỗi trường = đoạn giữa nhãn của nó và nhãn kế tiếp); sửa ký tự số
    thẻ, chuẩn hoá ngày, snap về giá trị chính thức; trả thêm tập trường "đoán theo mẫu chữ" khi không thấy nhãn.
  - `checks.py`: `card_design` nhận 3 mẫu thẻ: `2012`, `2026` (từ 14/06/2026 không in period_of_stay, permission_type,
    issuing_authority, permission_date, issue_date — chỉ lưu trong chip IC → trả `null`, `needs_review=false`),
    `specified_2026` (特定在留カード gộp My Number, chưa hỗ trợ → mọi trường `needs_review`). `assess_quality`: `low` khi
    conf TB < 0.9, > 20% dòng conf < 0.8, hoặc < 60% nhãn JP đọc được. `cross_check`: ngày sinh < ngày cấp, hết hạn ≥ ngày cấp…
  - `parser.py`: ghép các bước; fallback nhãn tiếng Anh (`_anchor_labels`: `NAME`, `DATE OF BIRTH`, `ADDRESS`…) →
    liệt kê ở `labels_from_english_anchor`, luôn `needs_review`.
  - `needs_review` khi: không đọc được, conf < 0.85, đã tự sửa, fail kiểm tra chéo, hoặc quality `low` (trường kanji).
- `static/`: UI HTML/JS thuần.

### vl_service/ (PaddleOCR-VL, cổng 8011)
- Tách riêng vì VL cần paddlepaddle 3.3.x, bản này crash PP-OCRv5 trên CPU (oneDNN). App chính pin 3.2.2.
- **Quyết định: chạy native trên host, không đưa vào Docker** (dù có `vl_service/Dockerfile`). Lý do: máy dev là Mac M4
  16GB, container phải chạy amd64 qua Rosetta (chậm hơn), và VL trên CPU nạp weight float32 cần > 8GB RAM cho Docker.
  Chạy (Python 3.10, `.venv` có sẵn), log luôn ghi vào `logs/vl_service.log` trong project (không để ở thư mục tạm):
  `cd vl_service && .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8011 >> ../logs/vl_service.log 2>&1`
- Mode `layout` (block có bbox) hoặc `whole` (không bbox).
- `vl_probe.py <ảnh> [pipeline_version]`: dev-only, in format/tốc độ output PaddleOCR-VL (chạy bằng `.venv` của vl_service).
- `.dockerignore` của app loại `vl_service/` và mọi `.venv` (venv VL ~1.1GB, trước đây bị gửi vào build context).

### scripts/, tests/
- `make_sample.py` sinh thẻ giả; `build_demo.py` tạo kết quả mẫu cho `static/samples`; `download_models.py` tải model khi build.
- `test_preprocess.py`: ảnh tổng hợp bằng OpenCV (thẻ nhạt màu nghiêng, bị che góc; ảnh đã cắt sát) + `estimate_skew`/`rotate`.
- Test parser dùng OCR fixture (`tests/fixtures/*.json`, đọc qua `parse_fixture`) hoặc box viết tay, không cần Paddle; `test_vl_client.py`
  dựng HTTP server giả thay cho vl_service.
