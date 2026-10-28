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
  log service → `logs/`, kết quả test/JSON trả về từ API → `samples/results/<tên ảnh>.<engine>.<mode>.json`.

## Tổng quan

Demo OCR mặt trước thẻ: thẻ cư trú Nhật (在留カード, `document=jp_residence`) và thẻ căn cước Việt Nam mẫu 2024 / CCCD gắn chip 2021
(`document=vn_id`). Upload hoặc chụp camera → JSON các trường. Chạy hoàn toàn local.

```
Upload → preprocess (EXIF rotate, tìm viền thẻ ID-1, cắt + nắn phẳng: dùng chung cho 2 loại thẻ)
       → OCR (engine=ppocr: PP-OCR theo ngôn ngữ thẻ ja|vi | engine=vl: PaddleOCR-VL qua vl_service, chỉ thẻ Nhật)
       → parse_residence_card | parse_vn_id_card (theo nhãn, + theo vị trí nếu mode=zone|hybrid)
       → kiểm tra chéo + đánh giá chất lượng → JSON
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
  "localhost:8000/api/extract?include_image=false&engine=ppocr&mode=hybrid" \
  > samples/results/residence_card_new_2026.ppocr.hybrid.json                          # engine=vl cần vl_service chạy
docker compose run --rm -v ./app/static:/app/app/static app python -m scripts.build_demo  # cập nhật static/samples
docker compose run --rm -v ./app/static:/app/app/static app python -m scripts.build_howto # ảnh cho how-it-works.html
curl -s -F file=@samples/vn/synthetic_1_photo.jpg \
  "localhost:8000/api/extract?include_image=false&mode=hybrid&document=vn_id" \
  > samples/results/vn_synthetic_1_photo.ppocr.hybrid.json
# thẻ VN giả: Docker không mount được /System/Library/Fonts → copy font tạm vào samples/vn/_font.ttf, chạy xong xoá
docker compose run --rm -v ./samples:/app/samples -v ./scripts:/app/scripts app \
  python -m scripts.make_sample_vn --font samples/vn/_font.ttf --person 1 --photo --out samples/vn/synthetic_1_photo.jpg
docker compose run --rm -e PYTHONPATH=/app -v ./app:/app/app -v ./tests:/app/tests -v ./scripts:/app/scripts app \
  python -m scripts.make_vn_fixtures samples/vn/synthetic_0.jpg                         # OCR → tests/fixtures/vn_*.json
```

Không có linter/formatter cấu hình sẵn.

Biến môi trường: `OCR_MODEL_SIZE`, `OCR_ENABLE_MKLDNN` (mặc định 1), `OCR_VI_DET_MODEL` / `OCR_VI_REC_MODEL` (model thẻ VN), `LOG_RESPONSES`, `LOG_FILE`, `DEBUG_SAVE_IMAGES`
(code mặc định 0, compose bật 1), `VL_URL`, `VL_MODE=layout|whole`, `VL_TIMEOUT_S` (600); vl_service:
`VL_PIPELINE_VERSION` (mặc định `v1.5`).

## Kiến trúc & logic

### app/ (FastAPI, Docker linux/amd64, cổng 8000)
Hướng phụ thuộc một chiều: `main` → `pipeline` → (`preprocess`, `ocr/*`, `residence_card/*`, `vn_id_card/*`) → `card_core/*`;
`ocr/types.OcrBox` là định dạng dòng OCR dùng chung (parser không import engine, engine không import parser; 2 package thẻ
không import nhau).
- `main.py`: chỉ lo HTTP: `/`, `/api/health` (model theo ngôn ngữ), `/api/zones?document=` (template toạ độ),
  `POST /api/extract?crop=&include_image=&engine=ppocr|vl&mode=label|zone|hybrid&document=jp_residence|vn_id`
  (`vl` + `zone`/`hybrid` → 422; `vl` + `vn_id` → 422). Giới hạn 10MB, 415 khi không đọc được ảnh, 503 khi engine=vl mà không gọi được vl_service.
  Lúc khởi động nạp sẵn mọi model trong `ppocr_model.MODELS` (2 model ~740MB RAM tổng).
- `pipeline.extract(img, original_size, crop, engine, mode, document)`: `DOCUMENTS` = loại thẻ → (hàm parse, ngôn ngữ OCR);
  `VL_DOCUMENTS` = loại thẻ cho phép engine=vl. Cắt/nắn → OCR → parse (truyền kích thước ảnh đã xử lý + `card_cropped`) → gắn `ocr` (engine, model, card_cropped,
  deskew_deg, size, lines) + `timing_ms` (preprocess không tính bước decode ảnh). API và `scripts/build_demo.py` cùng dùng.
- `config.py`: biến môi trường của app (log, VL). Riêng `OCR_MODEL_SIZE`/`OCR_ENABLE_MKLDNN` đọc trong `ocr/ppocr_model.py`.
- `request_log.py`: log 1 dòng tóm tắt/request (không có PII, có `doc=` loại thẻ). `LOG_RESPONSES=1` → ghi full kết quả vào `logs/extract.jsonl`;
  `DEBUG_SAVE_IMAGES=1` → lưu ảnh gốc + ảnh đã xử lý vào `logs/images/`. Cả hai chứa PII, compose đang bật mặc định.
- `preprocess.py`: OpenCV tìm 4 góc thẻ (`find_card`) và warp (`normalize_card`). `find_card` có 3 lần quét:
  (1) Canny 50/150 + `RETR_EXTERNAL`, sai lệch tỉ lệ < 0.25; (2) nếu lần 1 không thấy: Canny 20/60 + đóng khe hở
  (morph close 7×7) + `RETR_LIST` + convex hull (bắc qua góc bị ngón tay che), điều kiện chặt hơn (sai lệch tỉ lệ < 0.15,
  2 cạnh đối diện lệch ≤ 15%, diện tích 30–95% ảnh để không cắt nhầm vùng bên trong của ảnh đã cắt sát thẻ), rồi nới rộng
  4% vì hull hay lẹm vào thẻ. Lần 2 thêm vào cho ảnh thẻ nhạt màu trong bao nhựa (log `1.png`, 26/10/2026). Lần 1 giữ nguyên
  để không đổi kết quả các ảnh vốn đã chạy tốt. (3) `_find_card_textured` nếu 2 lần trên không thấy: thu về 600px, median blur 9,
  Canny trên từng kênh Lab (30/90 → 20/60 → 50/150), `RETR_LIST`, diện tích ≥ 8% ảnh, sai lệch tỉ lệ < 0.25 + 2 cạnh đối lệch ≤ 15%,
  nới 2%. Thêm cho ảnh thẻ CCCD chụp trên bàn gỗ, thẻ chỉ ~18% ảnh (log `6337de321938`, `fd35bf5e2740`, `87f5cca695f8`, 27/10/2026):
  ở cỡ gốc vân gỗ làm đứt viền thẻ và dính vào viền nên contour ngoài cùng thành hình thang; thẻ xanh vs gỗ cam khác nhau rõ về màu hơn độ sáng.
- `ocr/ppocr_model.py`: `MODELS` = ngôn ngữ → (det, rec), mỗi ngôn ngữ 1 instance + lock riêng (predictor không thread-safe),
  phân loại hướng 0/90/180/270. `ja`: PP-OCRv5 `OCR_MODEL_SIZE=server|mobile`. `vi`: det PP-OCRv5 + rec `PP-OCRv6_medium_rec`
  vì rec PP-OCRv5 (Trung/Nhật) bỏ hết dấu, `latin_PP-OCRv5_mobile_rec` mất chữ (`NGUYN`); det PP-OCRv6 nhanh hơn ~40% nhưng gộp
  nhãn + giá trị thành 1 dòng và làm mất "Nữ" (so bằng `scripts/bench_vi_rec.py`, kết quả `samples/results/vn_model_bench.txt`, 27/10/2026).
  **Không được import gì từ app**: Dockerfile chỉ copy file này (+ 2 `__init__.py` rỗng) vào layer tải model
  (`download_models.py` tải mọi ngôn ngữ), để sửa code khác không làm mất cache model.
- `ocr/ppocr.py` (`run_ocr(img, lang)`): sau OCR, `estimate_skew` lấy trung vị góc cạnh trên của các polygon chữ (`rec_polys`, chỉ
  box dài > 2× cao, cần ≥ 3 box); nếu 1°–30° thì xoay ảnh (`preprocess.rotate`, canvas nới rộng) và chiếu polygon theo,
  box trả về là bbox của polygon đã thẳng. Không OCR lại (recognition vốn đọc được quad nghiêng). Engine `vl` không có
  polygon → không nắn, chỉ nhờ `group_rows` chịu nghiêng.
- `ocr/vl_client.py`: gọi `VL_URL` (mặc định `host.docker.internal:8011`), tách block thành dòng `OcrBox`, score = 1.0
  (VL không trả confidence). Đọc `config.VL_URL` lúc gọi (test monkeypatch `config`).
- `card_core/`: phần chung, không biết chữ in của thẻ nào (normalize, regex nhãn, hàm trích trường do package thẻ truyền vào).
  Tách ra khi thêm thẻ VN; lúc tách đã so đầu ra parser thẻ Nhật trên mọi fixture × mode × crop: giống hệt.
  - `field.py`: `Field` (value, raw, confidence, needs_review, notes, source), `finish` (`needs_review` khi không đọc được,
    conf < 0.85 hoặc có note), `snap` về danh sách giá trị chính thức.
  - `layout.py`: `drop_non_text`, `group_rows`, `Document(boxes, normalize)` (text phẳng + map vị trí ký tự → score OCR).
    `group_rows` gom box theo đường có độ dốc, thử dốc −0.18…0.18 (~±10°) và chọn dốc cho ít dòng nhất, nhưng chỉ
    dùng khi ít hơn gom ngang ≥ 2 dòng (để thẻ thẳng không bị ảnh hưởng). Lý do: ảnh nghiêng vài độ làm lệch tâm dọc
    giữa nhãn và giá trị quá nửa chiều cao chữ, nhãn bị tách khỏi giá trị / ghép nhầm sang dòng khác.
  - `quality.py` (`assess_quality`): `low` khi conf TB < 0.9, > 20% dòng conf < 0.8, hoặc < 60% nhãn (ngôn ngữ chính của thẻ) đọc được.
  - `templates.py`: `load_templates`, `CARD_W`, `card_h`. Mỗi package thẻ có `data/templates.json`: toạ độ tương đối (0–1 theo thẻ) của nhãn
    (`label.<lang>` + `label.<lang>_box`, `<lang>` = `jp`|`vi`; thẻ Nhật thêm `en_box`), ô giá trị (`kind`, `en_box` dòng dịch, `shares_label`),
    vùng bỏ qua (ảnh, logo, dấu), và `anchors` (dòng in cố định, khung OCR thật của ảnh mẫu). Đo từ 1 ảnh mẫu mỗi loại → cần hiệu chỉnh trên ảnh thật.
  - `registration.py` (`register(boxes, template, page_size, cropped, normalize)`): khớp template vào ảnh. Ưu tiên mốc chữ: dòng OCR đọc ra đúng
    chữ của anchor (so khớp ≥ 0.85, ≤ 4 ký tự phải trùng, sau `normalize` của thẻ) → **tâm** khung ↔ tâm anchor, RANSAC similarity
    (`estimateAffinePartial2D`), homography nếu ≥ 4 mốc và giảm sai số ≥ 30%. Cần **≥ 3 mốc** (2 điểm luôn khớp tuyệt đối, không kiểm chứng được),
    sai số TB < 0.02 chiều rộng thẻ, |xoay| ≤ 30°, thẻ ≥ 20% chiều rộng ảnh. Không đủ mốc mà ảnh là thẻ đã nắn (`cropped`, tỉ lệ ảnh ≈ tỉ lệ thẻ ±0.02)
    → co giãn theo kích thước ảnh. Dùng tâm thay góc vì khung OCR rộng hẹp tuỳ lần đọc và góc lệch theo độ nghiêng.
  - `zones.py`: `ZoneSpec` (normalize, regex nhãn, regex cụm không được cắt, dòng chỉ là ký hiệu in, `label_lang`, hàm trích trường của mode nhãn).
    Chiếu từng dòng OCR về toạ độ thẻ; bỏ dòng trong vùng bỏ qua và dòng nhãn đọc lỗi (tâm trong ô nhãn, không có nhãn đọc được);
    bỏ ký tự đọc ra là nhãn. Dòng chạm 1 ô giá trị → lấy nguyên; chạm nhiều ô → chia: ước lượng x từng ký tự theo độ rộng (CJK 1, khác 0.55),
    ngày/số/từ đi thành cụm (không chia nguyên dòng vì khung OCR rộng hơn chữ, ước lượng hay lệch); cụm dính liền với nhãn
    (`NationalityViêt`) được cắt bỏ phần nhãn ở 2 đầu trước khi đặt vị trí. Text từng ô được dựng thành "thẻ ảo" (hàng `nhãn giá trị`)
    rồi chạy cùng hàm trích trường → làm sạch/chuẩn hoá giống hệt mode nhãn. `merge` (hybrid): giống nhau → `source=label+zone`;
    chỉ có theo vị trí → lấy, `needs_review`; khác nhau → giữ theo nhãn, `needs_review` + note. Trong 1 ô, mảnh chữ xếp theo hàng
    (`_reading_order`: cùng hàng = tâm cách mảnh đầu hàng ≤ 0.02 chiều cao thẻ) rồi trái → phải; trước đây làm tròn tâm nên 1 hàng bị
    tách ở ranh giới làm tròn (`An Khánh Son, Nam Dàn, Nghê`).
- `residence_card/` (thẻ Nhật): API công khai `parse_residence_card`, `group_rows`.
  - `patterns.py`: nhãn JP (`LABELS`), nhãn EN, regex, danh sách giá trị chính thức, bảng ký tự OCR hay nhầm, `normalize` (NFKC + chữ giản thể → kanji Nhật).
    Nhãn 在留資格 có lookahead loại `に基づく|変更|取得` (giá trị giới hạn lao động / loại phép chứa chữ này).
  - `fields.py`: `extract_fields` (giá trị mỗi trường = đoạn giữa nhãn của nó và nhãn kế tiếp); sửa ký tự số
    thẻ, chuẩn hoá ngày, snap về giá trị chính thức; trả thêm tập trường "đoán theo mẫu chữ" khi không thấy nhãn.
  - `checks.py`: `card_design` nhận 3 mẫu thẻ: `2012`, `2026` (từ 14/06/2026 không in period_of_stay, permission_type,
    issuing_authority, permission_date, issue_date — chỉ lưu trong chip IC → trả `null`, `needs_review=false`),
    `specified_2026` (特定在留カード gộp My Number, chưa hỗ trợ → mọi trường `needs_review`). `cross_check`: ngày sinh < ngày cấp, hết hạn ≥ ngày cấp…
  - `templates.py`: template mẫu `2012`, `2026` (ảnh mẫu ISA).
  - `parser.py`: ghép các bước + `ZONE_SPEC`; `mode=zone|hybrid` gọi registration/zones sau khi biết `card_design` (không có template cho `specified_2026`),
    kết quả ở `layout` (`mode`, `registration`, `zones_px`); `Field.source` = `label|zone|label+zone`. Fallback nhãn tiếng Anh (`_anchor_labels`: `NAME`, `DATE OF BIRTH`, `ADDRESS`…) →
    liệt kê ở `labels_from_english_anchor`, luôn `needs_review`.
  - `needs_review` khi: không đọc được, conf < 0.85, đã tự sửa, fail kiểm tra chéo, hoặc quality `low` (trường kanji).
- `vn_id_card/` (thẻ VN mặt trước, `document_type=vn_id_card`): API `parse_vn_id_card`. 2 mẫu (`patterns.DESIGNS`), chọn bằng
  `parser.card_design`: tiêu đề "CĂN CƯỚC CÔNG DÂN"/"Citizen Identity" → `cccd_2021` (CCCD gắn chip, 2021–06/2024, còn hiệu lực tới
  hạn in trên thẻ; mẫu mã vạch 2016 cùng tiêu đề nhưng chưa thử), còn lại → `2024` (thẻ căn cước từ 01/07/2024). Mỗi mẫu có nhãn
  (`LABEL_TEXTS[design]`), danh sách trường (`fields.FIELD_KEYS[design]`), template, tuổi đổi thẻ riêng; luồng xử lý chung.
  Trường: `id_number, full_name, date_of_birth, sex` (`Nam`/`Nữ`), `nationality, date_of_expiry` (ISO hoặc `"Không thời hạn"`);
  `cccd_2021` thêm `place_of_origin, place_of_residence` (in mặt trước). Mẫu 2024: nơi cư trú, nơi ĐK khai sinh, ngày cấp ở mặt sau → chưa hỗ trợ.
  Thêm `cccd_2021` khi người dùng chụp thẻ thật (log 27/10/2026): trước đó mọi thẻ VN bị đọc theo nhãn/template 2024 → quốc tịch
  nuốt cả quê quán + địa chỉ, họ tên rỗng, zone đặt sai ô.
  - `patterns.py`: nhãn in song ngữ trên 1 dòng (`Giới tính / Sex:`). `vi_pattern("gioi tinh")` sinh regex chịu lỗi OCR: mỗi chữ
    cái là lớp mọi biến thể có dấu (và `i`↔`j/l/1`), bỏ dấu cách/phẩy, thừa 1 chữ cuối từ (`chùr`), `u'`/`o'`/`ur` (`thurong`). Khớp trên **text gốc**
    (không bỏ dấu cả chuỗi) để vị trí ký tự giữ nguyên cho `zones`. Nửa tiếng Anh in nghiêng nhỏ, OCR đọc méo (`Dota ofbirt`,
    `Nationalty`) → regex lỏng nhưng phân biệt hoa thường (`(?-i:…)`) để không ăn vào giá trị in hoa. `LABELS` = cả nhãn
    (VN, EN hoặc cả hai; dấu `/` giữa 2 nửa OCR hay đọc thành `I`/`l`/`1`/`|` hoặc `/ I`); `VI_LABELS` để biết nhãn VN có đọc được không.
    Nhãn "Số" của `cccd_2021` chỉ 2 chữ → chỉ nhận khi ngay sau là `/ No` (`S6/No.3`, `SolNo.:`). Lookbehind trước nửa tiếng Anh dùng
    "không phải chữ Unicode" (không dùng `[A-Za-z]`: tiền tố `I ` sẽ ăn chữ `i` cuối của `Lợi`). `normalize` = NFC + khôi phục dấu móc: PP-OCR hay
    trả `HU'O'NG` cho `HƯƠNG`. `fold` (bỏ dấu, chữ thường) chỉ dùng để so khớp anchor/giá trị chuẩn. `PROVINCE_CODES` (63 mã tỉnh trước sáp nhập 2025),
    `CENTURY_SEX_DIGIT`, `RENEWAL_AGES[design]`. `foreign_letters`: chữ mang dấu không có trong tiếng Việt (`Ě` — PP-OCR đọc `Ễ` thành
    dấu móc ngược với conf cao) → họ tên `needs_review`.
  - `fields.py`: đoạn giữa nhãn như thẻ Nhật. Số định danh: 12 chữ số (sửa O→0, I→1…), tìm cả thẻ nếu không thấy nhãn. Họ tên: chuỗi
    từ in hoa dài nhất. Ngày hết hạn in dưới ảnh: hàng chứa nhãn của nó cũng chứa giới tính/quốc tịch nên ngày nằm hàng dưới →
    lấy ngày đầu tiên sau nhãn mà không phải ngày sinh. Nhãn "Có giá trị đến" in rất nhỏ, OCR hầu như không đọc được → khi không có nhãn
    ngày, các ngày còn lại: sớm nhất = ngày sinh, muộn nhất = hết hạn (đoán, `needs_review`). Giới tính/quốc tịch: so sau khi bỏ dấu,
    sai dấu thì sửa không đánh cờ (chỉ có 2 / 1 giá trị hợp lệ). Chỉ đọc được nửa tiếng Anh "Date of expiry" (in dưới nhãn VN) → lấy ngày
    gần nhất trước nó (cùng hàng hoặc hàng trên). Quê quán: đoạn tới nhãn kế tiếp; nơi thường trú (in 2 dòng, cuối thẻ, khối hạn thẻ dưới
    ảnh hay chen vào giữa): từ nhãn tới hết text, bỏ mọi nhãn, ngày tháng và nhãn ngày đọc méo (≤ 4 từ + `:` ngay trước ngày). Địa chỉ giữ
    nguyên dấu như OCR đọc (không có danh sách để đối chiếu).
  - `checks.py` `cross_check`: 3 số đầu ∈ mã tỉnh; số thứ 4 = thế kỷ sinh + giới tính (0/1 = 19xx nam/nữ, 2/3 = 20xx…);
    số 5–6 = 2 số cuối năm sinh; ngày hết hạn = sinh nhật tuổi 14/25/40/60 (`2024`, Luật Căn cước 2023, Điều 21) hoặc 25/40/60 (`cccd_2021`,
    Luật CCCD 2014, Điều 21); thẻ hết hạn; ngày sinh tương lai.
  - `data/templates.json` mẫu `2024`: đo trên `samples/vn/can_cuoc_2024_specimen.jpg` (ảnh thẻ mẫu trống đăng trên báo SGGP, 640×399,
    phóng lên 1600 rộng); anchors = tiêu đề, `CĂN`, `CƯỚC`, `Identity Card` và các dòng nhãn (bỏ "Độc lập - Tự do - Hạnh phúc": OCR chỉ khớp 0.82).
    Anchor so khớp sau `fold`. Độ phân giải ảnh mẫu thấp → cần hiệu chỉnh bằng ảnh thẻ thật. Mẫu `cccd_2021`: đo trên ảnh thẻ thật
    đã cắt (log `fd35bf5e2740`), quy đổi bỏ phần nới 2% của khung cắt; anchors gồm cả cụm lẫn từ đơn (`SOCIALIST`, `Citizen`…) vì PP-OCR
    lúc tách lúc gộp dòng tiêu đề (RANSAC loại mốc nhầm). Ô nơi thường trú phủ cả 2 dòng (chứa luôn ô nhãn), ô quê quán dòng dưới nhãn.
  - `parser.py`: như thẻ Nhật; `labels_from_english_anchor` = trường chỉ đọc được nửa tiếng Anh của nhãn (`needs_review`); ngày đoán
    theo mẫu chữ mà vị trí trên thẻ cho cùng kết quả (`label+zone`) thì không đánh cờ "đoán". Quality `low` → `full_name`, `nationality`,
    địa chỉ `needs_review`. `ZONE_SPECS[design]`.
  - Kết quả trên 4 ảnh thẻ CCCD 2021 thật (chụp trên bàn gỗ, `samples/results/vn_real_*`, git-ignore vì chứa dữ liệu cá nhân): hybrid
    8/8 trường, số/ngày/giới tính/quốc tịch đúng và khớp kiểm tra chéo; sai là dấu họ tên và địa chỉ.
  - Hạn chế đã biết: OCR sai dấu họ tên/địa chỉ (`NGUYÊN`/`NGUYỄN`, `HONG`/`HỒNG`, `Son`/`Sơn`, `Đ`→`D`) với conf vẫn cao; chỉ bắt được
    khi ra chữ không phải tiếng Việt (`foreign_letters`).
- `static/`: UI HTML/JS thuần (chọn loại giấy tờ `document`, nhớ trong localStorage; thẻ VN khoá engine VL; chọn `mode`, vẽ `zones_px`
  khi bật "Hiện ô template"; tên trường hiển thị theo `document_type`). Nút "Chụp ảnh bằng camera": `getUserMedia` (camera sau, xin
  độ phân giải tối đa, khung ngắm tỉ lệ ID-1, chụp ra JPEG rồi đi qua cùng luồng upload); chỉ chạy ở secure context (https/localhost) →
  mở từ điện thoại qua `http://<IP LAN>` thì rơi về `<input capture="environment">` (mở app camera của máy). `how-it-works.html` (link "Cách hoạt động"): giải thích luồng xử lý cho người non-tech,
  ảnh minh hoạ thật trong `static/howto/` sinh bằng `scripts/build_howto.py` → **đổi luồng preprocess/OCR/parse thì cập nhật
  trang này** và chạy lại script. `design.html` (link "Thiết kế (review)" ở trang chủ) (vẽ template từ `/api/zones`): bản thiết kế đoán giá trị theo
  danh sách/vị trí: mục ★ (template + mode zone/hybrid) đã triển khai, mục 0–6 **chưa**. Khi làm mục nào thì cập nhật cả trang này lẫn phần kiến trúc ở trên.

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
- `make_sample.py` sinh thẻ giả; `make_sample_vn.py` in dữ liệu giả (số định danh đúng quy tắc) lên ảnh mẫu thẻ căn cước;
  `make_vn_fixtures.py` OCR ảnh → `tests/fixtures/vn_*.json`; `bench_vi_rec.py` so các cặp model det/rec trên ảnh thẻ VN; `build_demo.py` tạo kết quả mẫu cho `static/samples`; `build_howto.py` đặt thẻ mẫu ISA
  vào ảnh giả lập (xiên, nền cùng màu, chụp sát nghiêng), chạy pipeline thật, ghi ảnh + `summary.json` vào `static/howto`; `download_models.py` tải model khi build.
- `test_vn_id_card.py`: thẻ VN trên box viết tay + fixture OCR thật (nhãn bị đọc méo, ư/ơ thành u'/o', ngày hết hạn dưới ảnh,
  zone/hybrid trên ảnh chụp, kiểm tra chéo số định danh/hạn thẻ); `cccd_2021` trên box viết tay (người giả) và fixture OCR ảnh thật
  `tests/fixtures/vn_real2021_*.json` (git-ignore, chứa PII; test chỉ kiểm cấu trúc + kiểm tra chéo, không ghi giá trị thật; tự skip khi thiếu).
- `test_zones.py`: mode zone/hybrid trên fixture (trùng mode nhãn, thẻ nhỏ + nghiêng, mất nhãn, < 3 mốc, crop).
- `test_preprocess.py`: ảnh tổng hợp bằng OpenCV (thẻ nhạt màu nghiêng, bị che góc; ảnh đã cắt sát) + `estimate_skew`/`rotate`.
- Test parser dùng OCR fixture (`tests/fixtures/*.json`, đọc qua `parse_fixture`) hoặc box viết tay, không cần Paddle; `test_vl_client.py`
  dựng HTTP server giả thay cho vl_service.
