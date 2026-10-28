# OCR giấy tờ Nhật demo

Website demo: upload hoặc chụp bằng camera ảnh **giấy tờ Nhật** (thẻ cư trú 在留カード, My Number, bằng lái, hộ chiếu, thẻ bảo hiểm y tế;
mỗi loại chỉ lấy vài trường, xem tab "Giấy tờ hỗ trợ") → trích xuất thông tin ra JSON. OCR bằng PaddleOCR (PP-OCRv5), trích xuất trường bằng rule. Chạy hoàn toàn local, ảnh chỉ xử lý trong bộ nhớ.

Chọn/kéo thả/dán ảnh hoặc chụp xong chỉ hiện ảnh xem trước; chọn loại giấy tờ + tuỳ chọn rồi bấm **Nhận dạng** để chạy
(đổi tuỳ chọn rồi bấm lại được, không cần chọn lại ảnh).

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

### Deploy lên server GPU (AWS EC2 g6.xlarge, không Docker)

Xem [`deploy/aws-ec2-gpu/README.md`](deploy/aws-ec2-gpu/README.md): script `install.sh` cài `paddlepaddle-gpu`, service
systemd cho app + PaddleOCR-VL, tuỳ chọn HTTPS (Caddy) + mật khẩu. Chọn thiết bị bằng `OCR_DEVICE` / `VL_DEVICE`
(`gpu:0` | `cpu`, mặc định Paddle tự chọn); `GET /api/health` trả `device` đang dùng.

## API

```bash
curl -F file=@samples/synthetic_photo.jpg "localhost:8000/api/extract?include_image=false"
```

| Query param | Mặc định | Ý nghĩa |
|---|---|---|
| `document` | `jp_residence` | `auto` (tự nhận diện loại giấy tờ từ chữ OCR; không nhận ra → 422; UI mặc định dùng `auto`) hoặc chọn loại: giấy tờ Nhật `jp_residence` (thẻ cư trú, chỉ số thẻ), `jp_mynumber` (My Number), `jp_driver_license` (bằng lái), `jp_passport` (hộ chiếu Nhật, không tự cắt ảnh), `jp_health_insurance` (thẻ bảo hiểm y tế / 資格確認書) |
| `crop` | `true` | Tự tìm viền thẻ, cắt và nắn phẳng (kể cả thẻ nhạt màu, trong bao nhựa, bị che 1 góc, thẻ nhỏ trên nền vân gỗ) |
| `include_image` | `true` | Trả kèm ảnh đã xử lý (base64) để hiển thị |
| `engine` | `ppocr` | `ppocr` (PP-OCRv5, trong container) hoặc `vl` (PaddleOCR-VL, cần `vl_service` đang chạy, nếu không trả 503) |
| `mode` | `label` | Cách xác định trường: `label` (chữ sau nhãn in sẵn), `zone` (chữ nằm trong ô cố định của mẫu thẻ), `hybrid` (cả hai: vị trí bù chỗ nhãn không đọc được, hai cách khác nhau thì `needs_review`). `zone`/`hybrid` chỉ với `engine=ppocr` (VL trả 422) |

Mỗi trường trả về dạng:

```json
"date_of_birth": { "value": "1995-04-12", "raw": "1995年04月12日", "confidence": 0.9997, "needs_review": false, "notes": [], "source": "label" }
```

Các trường (`document_type` cho biết loại thẻ):
- `residence_card`: chỉ `card_number` (các mục khác vẫn đọc nội bộ để nhận mẫu thẻ, không trả về).
- `my_number_card` (mặt trước thẻ My Number): chỉ `issuer` (nơi cấp, in dạng `○○市長`/`○○区長`/`○○町長`/`○○村長`) và
  `expiry_date` (ngày ISO, từ dòng `YYYY年 M月 D日まで有効`). Không có template → `zone`/`hybrid` chạy như `label` kèm warning.
- `driver_license`: `license_number` (12 chữ số trong `第…号`), `issue_date` (ngày sau `交付`, ISO).
- `passport` (hộ chiếu Nhật): `passport_number` (2 chữ + 7 số; kiểm bằng check digit của dòng MRZ khi đọc được).
- `health_insurance_card`: `card_type` (tên thẻ như in, vd `国民健康保険被保険者証`), `insurer_name` (`保険者名称` / `交付者名`), `issue_date` (ISO).
- Các loại `my_number_card`, `driver_license`, `passport`, `health_insurance_card` đọc theo nhãn/mẫu chữ, chưa có template: `zone`/`hybrid` chạy như `label` kèm warning.

Mọi kết quả có `document` (loại đã đọc). Với `document=auto` có thêm `document_detection`: `detected`, `confident`
(false khi loại thứ hai gần điểm → kèm warning), `scores` theo từng loại.

`source`: `label` (theo nhãn), `zone` (theo vị trí), `label+zone` (hai cách cho cùng kết quả). `layout` cho biết mode,
kết quả khớp mẫu thẻ vào ảnh (`registration`: số mốc dùng, sai số, góc xoay; `null` nếu không khớp được → chỉ dùng kết quả
theo nhãn kèm warning) và `zones_px` (ô giá trị đã chiếu vào ảnh, để vẽ). `GET /api/zones?document=jp_residence` (loại khác trả `{}`) trả
template toạ độ của các mẫu thẻ. `GET /api/health` liệt kê model OCR theo ngôn ngữ và thiết bị (`device`: `cpu`/`gpu:0`).

`ocr.card_cropped` cho biết đã tìm được viền thẻ để cắt hay chưa; `ocr.deskew_deg` là góc nghiêng (độ) đã được nắn
thẳng dựa trên hướng các dòng chữ khi ảnh còn nghiêng (thường là ảnh không tìm được viền thẻ; chỉ engine `ppocr`), 0 nếu không nắn.

`needs_review = true` khi: không đọc được, độ tin cậy OCR < 0.85, đã tự sửa ký tự, hoặc không qua kiểm tra chéo
(thẻ cư trú: ngày sinh < ngày cấp, hết hạn ≥ ngày cấp…; bằng lái: mã công an tỉnh; hộ chiếu: check digit MRZ).

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
    ppocr_model.py     Khởi tạo PP-OCR (ja) 1 instance (dùng riêng ở bước tải model khi build image)
    ppocr.py           Engine PP-OCR (+ phân loại hướng 0/90/180/270, nắn ảnh nghiêng ≤ 30°)
    vl_client.py       Engine PaddleOCR-VL (gọi vl_service qua HTTP)
  card_core/           Phần chung mọi loại thẻ: gom dòng (layout), Field, chất lượng OCR, khớp template (registration), đọc theo ô (zones)
  residence_card/      Thẻ cư trú Nhật: 氏名, 生年月日, 住居地, 在留資格...
    patterns.py        Nhãn, regex, danh sách giá trị chính thức, ký tự OCR hay nhầm
    fields.py          Trích từng trường
    checks.py          Nhận mẫu thẻ, đánh giá chất lượng ảnh, kiểm tra chéo ngày tháng
    parser.py          parse_residence_card: ghép các bước trên
  my_number_card/      Thẻ My Number: chỉ nơi cấp + hạn thẻ, đọc theo mẫu chữ (patterns, parser)
  driver_license/      Bằng lái Nhật: số + ngày cấp
  passport/            Hộ chiếu Nhật: số hộ chiếu (MRZ + số in)
  health_insurance/    Thẻ bảo hiểm y tế Nhật: loại thẻ, đơn vị bảo hiểm, ngày cấp
  static/              Giao diện (HTML/JS thuần); how-it-works.html giải thích cách hoạt động cho người không chuyên; tab "Giấy tờ hỗ trợ" (docs.js) liệt kê giấy tờ Nhật + trường lấy được kèm hình minh hoạ
scripts/               make_sample (sinh thẻ giả), build_demo (chạy ảnh mẫu chính thức → tab "Mẫu chính thức"), build_howto (ảnh minh hoạ), download_models
vl_service/            Service PaddleOCR-VL (chạy native trên host, cổng 8011) + vl_probe.py
deploy/aws-ec2-gpu/    install.sh + hướng dẫn deploy native lên EC2 GPU (systemd, Caddy)
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
- `samples/synthetic_*.jpg` là thẻ **giả lập** với dữ liệu giả, layout chỉ gần giống thẻ thật. Độ chính xác trên ảnh thật cần đo lại.
- Ảnh mẫu chính thức (見本, dữ liệu giả do cơ quan Nhật công bố): `samples/isa/` (thẻ cư trú, Cục Xuất nhập cảnh) và `samples/official/`
  (My Number, bằng lái, hộ chiếu, 資格確認書 — nguồn trong `samples/official/SOURCES.md`). Xem kết quả ở tab "Mẫu chính thức".
