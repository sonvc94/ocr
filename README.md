# OCR thẻ demo: 在留カード · Thẻ căn cước VN

Website demo: upload hoặc chụp bằng camera ảnh **mặt trước thẻ cư trú Nhật (在留カード)** hoặc **thẻ căn cước Việt Nam
(mẫu 2024 và Căn cước công dân gắn chip 2021)** → trích xuất thông tin ra JSON. OCR bằng PaddleOCR (PP-OCRv5 cho tiếng Nhật, PP-OCRv6 cho
nhận dạng tiếng Việt có dấu), trích xuất trường bằng rule. Chạy hoàn toàn local, ảnh chỉ xử lý trong bộ nhớ.

Nút **📷 Chụp ảnh bằng camera**: trên `localhost`/HTTPS mở camera ngay trong trang (có khung ngắm theo tỉ lệ thẻ);
mở từ điện thoại qua `http://<IP máy>:8000` thì trình duyệt không cho dùng camera trong trang, nút này mở app camera của máy.

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
| `document` | `jp_residence` | `jp_residence` (thẻ cư trú Nhật) hoặc `vn_id` (thẻ căn cước VN mẫu 2024 / CCCD gắn chip 2021, chỉ `engine=ppocr`, `vl` trả 422) |
| `crop` | `true` | Tự tìm viền thẻ, cắt và nắn phẳng (kể cả thẻ nhạt màu, trong bao nhựa, bị che 1 góc, thẻ nhỏ trên nền vân gỗ) |
| `include_image` | `true` | Trả kèm ảnh đã xử lý (base64) để hiển thị |
| `engine` | `ppocr` | `ppocr` (PP-OCRv5, trong container) hoặc `vl` (PaddleOCR-VL, cần `vl_service` đang chạy, nếu không trả 503) |
| `mode` | `label` | Cách xác định trường: `label` (chữ sau nhãn in sẵn), `zone` (chữ nằm trong ô cố định của mẫu thẻ), `hybrid` (cả hai: vị trí bù chỗ nhãn không đọc được, hai cách khác nhau thì `needs_review`). `zone`/`hybrid` chỉ với `engine=ppocr` (VL trả 422) |

Mỗi trường trả về dạng:

```json
"date_of_birth": { "value": "1995-04-12", "raw": "1995年04月12日", "confidence": 0.9997, "needs_review": false, "notes": [], "source": "label" }
```

Các trường (`document_type` cho biết loại thẻ):
- `residence_card`: `card_number, name, date_of_birth, sex, nationality, address, status_of_residence, work_restriction,
  period_of_stay, expiration_date, permission_type, issuing_authority, permission_date, issue_date, valid_until`.
- `vn_id_card`: `id_number, full_name, date_of_birth, sex` (`Nam`/`Nữ`), `nationality, date_of_expiry` (ngày ISO hoặc
  `"Không thời hạn"`). `card_design`: `2024` (thẻ căn cước từ 01/07/2024) hoặc `cccd_2021` (Căn cước công dân gắn chip), tự nhận
  theo tiêu đề thẻ. `cccd_2021` có thêm `place_of_origin` (quê quán), `place_of_residence` (nơi thường trú). Mẫu 2024: nơi cư trú,
  nơi đăng ký khai sinh, ngày cấp in ở mặt sau, chưa hỗ trợ. Họ tên có chữ mang dấu không có trong tiếng Việt (OCR đọc sai dấu)
  luôn `needs_review`.

`source`: `label` (theo nhãn), `zone` (theo vị trí), `label+zone` (hai cách cho cùng kết quả). `layout` cho biết mode,
kết quả khớp mẫu thẻ vào ảnh (`registration`: số mốc dùng, sai số, góc xoay; `null` nếu không khớp được → chỉ dùng kết quả
theo nhãn kèm warning) và `zones_px` (ô giá trị đã chiếu vào ảnh, để vẽ). `GET /api/zones?document=jp_residence|vn_id` trả
template toạ độ của các mẫu thẻ. `GET /api/health` liệt kê model OCR theo ngôn ngữ.

`ocr.card_cropped` cho biết đã tìm được viền thẻ để cắt hay chưa; `ocr.deskew_deg` là góc nghiêng (độ) đã được nắn
thẳng dựa trên hướng các dòng chữ khi ảnh còn nghiêng (thường là ảnh không tìm được viền thẻ; chỉ engine `ppocr`), 0 nếu không nắn.

`needs_review = true` khi: không đọc được, độ tin cậy OCR < 0.85, đã tự sửa ký tự, hoặc không qua kiểm tra chéo
(thẻ Nhật: ngày sinh < ngày cấp, hết hạn ≥ ngày cấp…; thẻ VN: 3 số đầu số định danh là mã tỉnh, số thứ 4 khớp giới tính +
thế kỷ sinh, số 5–6 khớp năm sinh, ngày hết hạn trùng sinh nhật tuổi 14/25/40/60).

Thẻ VN: OCR hay đọc sai dấu tiếng Việt (`NGUYÊN` thay vì `NGUYỄN`) mà vẫn tự tin cao, nên **họ tên luôn cần người
đối chiếu** dù không bị đánh dấu.

## Cấu trúc

```
app/
  main.py              FastAPI: /, /api/health, /api/zones, /api/extract (chỉ nhận request, trả lỗi HTTP)
  pipeline.py          Luồng xử lý chung: cắt/nắn thẻ → OCR (theo ngôn ngữ thẻ) → parse → JSON (API và scripts cùng dùng)
  config.py            Biến môi trường của app
  request_log.py       Log tóm tắt mỗi request, ghi kết quả/ảnh để debug (khi bật)
  preprocess.py        EXIF rotate, tìm & nắn thẻ, ước lượng/xoay góc nghiêng (OpenCV)
  ocr/
    types.py           OcrBox: định dạng dòng OCR dùng chung giữa engine và parser
    ppocr_model.py     Khởi tạo PP-OCR mỗi ngôn ngữ 1 instance: ja, vi (dùng riêng ở bước tải model khi build image)
    ppocr.py           Engine PP-OCR (+ phân loại hướng 0/90/180/270, nắn ảnh nghiêng ≤ 30°)
    vl_client.py       Engine PaddleOCR-VL (gọi vl_service qua HTTP)
  card_core/           Phần chung mọi loại thẻ: gom dòng (layout), Field, chất lượng OCR, khớp template (registration), đọc theo ô (zones)
  residence_card/      Thẻ cư trú Nhật: 氏名, 生年月日, 住居地, 在留資格...
    patterns.py        Nhãn, regex, danh sách giá trị chính thức, ký tự OCR hay nhầm
    fields.py          Trích từng trường
    checks.py          Nhận mẫu thẻ, đánh giá chất lượng ảnh, kiểm tra chéo ngày tháng
    parser.py          parse_residence_card: ghép các bước trên
  vn_id_card/          Thẻ căn cước VN 2024 + CCCD gắn chip 2021: cùng cấu trúc (patterns, fields, checks, parser, data/templates.json)
  static/              Giao diện (HTML/JS thuần); how-it-works.html giải thích cách hoạt động cho người không chuyên
scripts/               make_sample / make_sample_vn (sinh thẻ giả), build_demo (kết quả mẫu cho UI), build_howto (ảnh minh hoạ),
                       download_models, bench_vi_rec (so model OCR tiếng Việt), make_vn_fixtures (OCR → fixture test)
vl_service/            Service PaddleOCR-VL (chạy native trên host, cổng 8011) + vl_probe.py
tests/                 Test parser, tìm viền/nắn nghiêng, vl_client (không cần Paddle)
```

Test: `docker compose run --rm app python -m pytest -q`

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
- Thẻ VN: `samples/vn/can_cuoc_2024_specimen.jpg` là ảnh mẫu thẻ trống đăng trên báo (SGGP, 640×399); `synthetic_*.jpg`
  in dữ liệu giả lên ảnh này (`scripts/make_sample_vn.py`, cần font có dấu tiếng Việt). Template đo trên ảnh mẫu độ phân
  giải thấp → cần hiệu chỉnh bằng ảnh thẻ thật.
