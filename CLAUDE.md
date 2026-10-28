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

Demo OCR mặt trước giấy tờ. Nhật (người dùng chỉ cần vài trường mỗi loại, 28/10/2026): thẻ cư trú (在留カード, `document=jp_residence`,
chỉ số thẻ), My Number (個人番号カード, `jp_mynumber`, nơi cấp + hạn thẻ), bằng lái (運転免許証, `jp_driver_license`, số 12 chữ số + ngày cấp),
hộ chiếu Nhật (旅券, `jp_passport`, số hộ chiếu), thẻ bảo hiểm y tế (健康保険証/資格確認書, `jp_health_insurance`, loại thẻ + đơn vị bảo hiểm
+ ngày cấp). Hỗ trợ thẻ căn cước Việt Nam đã bị gỡ (28/10/2026, theo yêu cầu; code cũ trong git history trước commit gỡ). Upload hoặc chụp camera → JSON các trường. Chạy hoàn toàn local.

```
Upload → preprocess (EXIF rotate, tìm viền thẻ ID-1, cắt + nắn phẳng: dùng chung, trừ hộ chiếu)
       → OCR (engine=ppocr: PP-OCRv5 tiếng Nhật | engine=vl: PaddleOCR-VL qua vl_service)
       → (document=auto: detect.py chọn loại giấy tờ từ chữ OCR)
       → parser theo loại giấy tờ (theo nhãn/mẫu chữ, + theo vị trí nếu mode=zone|hybrid và loại đó có template)
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
docker compose run --rm -v ./app:/app/app -v ./scripts:/app/scripts app python -m scripts.build_demo  # cập nhật static/samples (rồi --build)
docker compose run --rm -v ./app:/app/app -v ./scripts:/app/scripts app python -m scripts.build_howto  # ảnh cho tab "Luồng xử lý"
```

Không có linter/formatter cấu hình sẵn.

Biến môi trường: `OCR_MODEL_SIZE`, `OCR_ENABLE_MKLDNN` (mặc định 1, chỉ có tác dụng trên CPU), `OCR_DEVICE` (`gpu:0`|`cpu`, không đặt = Paddle tự chọn), `LOG_RESPONSES`, `LOG_FILE`, `DEBUG_SAVE_IMAGES`
(code mặc định 0, compose bật 1), `VL_URL`, `VL_MODE=layout|whole`, `VL_TIMEOUT_S` (600); vl_service:
`VL_PIPELINE_VERSION` (mặc định `v1.5`), `VL_DEVICE`.

## Kiến trúc & logic

### app/ (FastAPI, Docker linux/amd64, cổng 8000)
Hướng phụ thuộc một chiều: `main` → `pipeline` → (`preprocess`, `ocr/*`, package từng giấy tờ: `residence_card`, `my_number_card`,
`driver_license`, `passport`, `health_insurance`) → `card_core/*`;
`ocr/types.OcrBox` là định dạng dòng OCR dùng chung (parser không import engine, engine không import parser; 2 package thẻ
không import nhau).
- `main.py`: chỉ lo HTTP: `/`, `/api/health` (model theo ngôn ngữ, `device` thật đang chạy), `/api/zones?document=` (template toạ độ),
  `POST /api/extract?crop=&include_image=&engine=ppocr|vl&mode=label|zone|hybrid&document=auto|<khoá của pipeline.DOCUMENTS>`
  (`vl` + `zone`/`hybrid` → 422; `auto` không nhận ra → 422 + log điểm). API mặc định vẫn `jp_residence` (không đổi hành vi client cũ), UI mặc định `auto`. `/api/zones` chỉ có template cho `jp_residence`; loại khác trả `{}`. Giới hạn 10MB, 415 khi không đọc được ảnh, 503 khi engine=vl mà không gọi được vl_service.
  Lúc khởi động nạp sẵn mọi model trong `ppocr_model.MODELS` (hiện chỉ `ja`).
- `pipeline.extract(img, original_size, crop, engine, mode, document)`: `DOCUMENTS` = loại giấy tờ → (hàm parse, ngôn ngữ OCR, có cắt thẻ ID-1 không).
  `jp_residence` = `partial(parse_residence_card, keys=("card_number",))`. `jp_passport` không cắt: trang hộ chiếu là ID-3, chụp mở
  2 trang thì tỉ lệ gần bằng 1 trang → dễ cắt nhầm cả cuốn; MRZ/nhãn đọc được trên ảnh nguyên. Mọi loại đều cho phép engine=vl. Mọi kết quả có `document` (loại đã parse).
  `document=auto` (`DOCUMENT_CHOICES`): cắt thẻ ID-1 → OCR `ja` (`_ocr`) → `detect.detect_document` → nếu ra hộ chiếu mà ảnh đã bị cắt thì OCR lại
  ảnh gốc (như `jp_passport`; 2 lần OCR) → parse; thêm `document_detection` (`detected`, `confident`, `scores`), không chắc → warning;
  không loại nào đạt ngưỡng → `UnknownDocument`. Cắt/nắn → OCR → parse (truyền kích thước ảnh đã xử lý + `card_cropped`) → gắn `ocr` (engine, model, card_cropped,
  deskew_deg, size, lines) + `timing_ms` (preprocess không tính bước decode ảnh). API và `scripts/build_demo.py` cùng dùng.
- `detect.py`: `MARKERS` = loại giấy tờ → [(regex chữ in, điểm)]: tiêu đề 3 (在留カード, 個人番号カード, 運転免許証, 公安委員会, MRZ `P<JPN` / dòng 2,
  …被保険者証/資格確認書), nhãn riêng 1–2 (在留資格, 電子証明書, 第…号, 旅券番号, 保険者番号…). Bỏ chữ in trên nhiều loại (氏名, 住所, まで有効, 日本国).
  So trên text đã gom dòng (`Document` + `jp_normalize`: OCR hay tách `個人番号`|`カード` thành 2 khung). Chọn điểm cao nhất nếu ≥ `MIN_SCORE` 3;
  `confident` khi điểm nhì < 75% điểm nhất. 特定在留カード có thêm `特定在留` để thắng My Number. Kiểm trên OCR thật của 9 ảnh mẫu (`tests/test_detect.py`)
  + API trên 8 ảnh mẫu (`samples/results/*.ppocr.auto.json`): đúng hết, đều `confident`.
- `config.py`: biến môi trường của app (log, VL). Riêng `OCR_MODEL_SIZE`/`OCR_ENABLE_MKLDNN`/`OCR_DEVICE` đọc trong `ocr/ppocr_model.py`.
- `request_log.py`: log 1 dòng tóm tắt/request (không có PII, có `doc=` loại thẻ). `LOG_RESPONSES=1` → ghi full kết quả vào `logs/extract.jsonl`;
  `DEBUG_SAVE_IMAGES=1` → lưu ảnh gốc + ảnh đã xử lý vào `logs/images/`. Cả hai chứa PII, compose đang bật mặc định.
- `preprocess.py`: OpenCV tìm 4 góc thẻ (`find_card`) và warp (`normalize_card`). `find_card` có 3 lần quét:
  (1) Canny 50/150 + `RETR_EXTERNAL`, sai lệch tỉ lệ < 0.25; (2) nếu lần 1 không thấy: Canny 20/60 + đóng khe hở
  (morph close 7×7) + `RETR_LIST` + convex hull (bắc qua góc bị ngón tay che), điều kiện chặt hơn (sai lệch tỉ lệ < 0.15,
  2 cạnh đối diện lệch ≤ 15%, diện tích 30–95% ảnh để không cắt nhầm vùng bên trong của ảnh đã cắt sát thẻ), rồi nới rộng
  4% vì hull hay lẹm vào thẻ. Lần 2 thêm vào cho ảnh thẻ nhạt màu trong bao nhựa (log `1.png`, 26/10/2026). Lần 1 giữ nguyên
  để không đổi kết quả các ảnh vốn đã chạy tốt. (3) `_find_card_textured` nếu 2 lần trên không thấy: thu về 600px, median blur 9,
  Canny trên từng kênh Lab (30/90 → 20/60 → 50/150), `RETR_LIST`, diện tích ≥ 8% ảnh, sai lệch tỉ lệ < 0.25 + 2 cạnh đối lệch ≤ 15%,
  nới 2%. Thêm cho ảnh thẻ chụp trên bàn gỗ (ảnh CCCD VN thật, lúc còn hỗ trợ thẻ VN), thẻ chỉ ~18% ảnh (log `6337de321938`, `fd35bf5e2740`, `87f5cca695f8`, 27/10/2026):
  ở cỡ gốc vân gỗ làm đứt viền thẻ và dính vào viền nên contour ngoài cùng thành hình thang; thẻ xanh vs gỗ cam khác nhau rõ về màu hơn độ sáng.
- `ocr/ppocr_model.py`: `MODELS` = ngôn ngữ → (det, rec), mỗi ngôn ngữ 1 instance + lock riêng (predictor không thread-safe),
  phân loại hướng 0/90/180/270, `device=OCR_DEVICE` (`device_name()` cho health). `ja`: PP-OCRv5 `OCR_MODEL_SIZE=server|mobile`.
  **Không được import gì từ app**: Dockerfile chỉ copy file này (+ 2 `__init__.py` rỗng) vào layer tải model
  (`download_models.py` tải mọi ngôn ngữ), để sửa code khác không làm mất cache model.
- `ocr/ppocr.py` (`run_ocr(img, lang)`): sau OCR, `estimate_skew` lấy trung vị góc cạnh trên của các polygon chữ (`rec_polys`, chỉ
  box dài > 2× cao, cần ≥ 3 box); nếu 1°–30° thì xoay ảnh (`preprocess.rotate`, canvas nới rộng) và chiếu polygon theo,
  box trả về là bbox của polygon đã thẳng. Không OCR lại (recognition vốn đọc được quad nghiêng). Engine `vl` không có
  polygon → không nắn, chỉ nhờ `group_rows` chịu nghiêng.
- `ocr/vl_client.py`: gọi `VL_URL` (mặc định `host.docker.internal:8011`), tách block thành dòng `OcrBox`, score = 1.0
  (VL không trả confidence). Đọc `config.VL_URL` lúc gọi (test monkeypatch `config`).
- `card_core/`: phần chung, không biết chữ in của thẻ nào (normalize, regex nhãn, hàm trích trường do package thẻ truyền vào).
  Tách ra khi thêm thẻ VN (nay đã gỡ); lúc tách đã so đầu ra parser thẻ Nhật trên mọi fixture × mode × crop: giống hệt.
  - `field.py`: `Field` (value, raw, confidence, needs_review, notes, source), `finish` (`needs_review` khi không đọc được,
    conf < 0.85 hoặc có note), `snap` về danh sách giá trị chính thức.
  - `layout.py`: `drop_non_text`, `group_rows`, `Document(boxes, normalize)` (text phẳng + map vị trí ký tự → score OCR).
    `group_rows` gom box theo đường có độ dốc, thử dốc −0.18…0.18 (~±10°) và chọn dốc cho ít dòng nhất, nhưng chỉ
    dùng khi ít hơn gom ngang ≥ 2 dòng (để thẻ thẳng không bị ảnh hưởng). Lý do: ảnh nghiêng vài độ làm lệch tâm dọc
    giữa nhãn và giá trị quá nửa chiều cao chữ, nhãn bị tách khỏi giá trị / ghép nhầm sang dòng khác.
  - `quality.py` (`assess_quality`): `low` khi conf TB < 0.9, > 20% dòng conf < 0.8, hoặc < 60% nhãn (ngôn ngữ chính của thẻ) đọc được.
  - `templates.py`: `load_templates`, `CARD_W`, `card_h`. Mỗi package thẻ có `data/templates.json`: toạ độ tương đối (0–1 theo thẻ) của nhãn
    (`label.<lang>` + `label.<lang>_box`, `<lang>` = `jp`; thêm `en_box` dòng tiếng Anh), ô giá trị (`kind`, `en_box` dòng dịch, `shares_label`),
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
    (`NAMEJOHN`) được cắt bỏ phần nhãn ở 2 đầu trước khi đặt vị trí. Text từng ô được dựng thành "thẻ ảo" (hàng `nhãn giá trị`)
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
  - `parser.py` `parse_residence_card(..., keys=None)`: `keys` giới hạn trường trả về (API chỉ trả `card_number` theo yêu cầu 28/10/2026);
    vẫn đọc mọi trường (nhận mẫu thẻ, chất lượng cần chúng) nhưng bỏ `cross_check` giữa các ngày và lọc `zones_px`. Test gọi không có `keys` (đủ trường).
    Ghép các bước + `ZONE_SPEC`; `mode=zone|hybrid` gọi registration/zones sau khi biết `card_design` (không có template cho `specified_2026`),
    kết quả ở `layout` (`mode`, `registration`, `zones_px`); `Field.source` = `label|zone|label+zone`. Fallback nhãn tiếng Anh (`_anchor_labels`: `NAME`, `DATE OF BIRTH`, `ADDRESS`…) →
    liệt kê ở `labels_from_english_anchor`, luôn `needs_review`.
  - `needs_review` khi: không đọc được, conf < 0.85, đã tự sửa, fail kiểm tra chéo, hoặc quality `low` (trường kanji).
- `my_number_card/` (thẻ My Number mặt trước, `document_type=my_number_card`, OCR `ja`): API `parse_my_number_card`. Người dùng chỉ cần
  2 trường (28/10/2026): `issuer` và `expiry_date`; các trường khác trên thẻ (họ tên, địa chỉ, ngày sinh, giới tính) cố ý không lấy.
  Cả 2 không có nhãn in sẵn → đọc theo mẫu chữ trên text phẳng (`Document`), không template, `mode=zone|hybrid` chạy như `label` + warning.
  Dùng chung `card_core/pattern_card.py` với 3 package bên dưới: `JP_DATE_RE`/`jp_date` (năm 西暦 hoặc 令和/平成/昭和/元年, cả dạng `R5. 4. 1`;
  năm < 1900 không có niên hiệu → `None`), `jp_normalize` (NFKC + `SIMPLIFIED_TO_JP`: PP-OCRv5 hay trả chữ giản thể — trên ảnh mẫu chính thức
  gặp `まで有效`, `公安委员会`; mọi `normalize` của 4 package này gọi nó), `build_result` (cùng dạng kết quả parser có template; quality `low` → mọi trường có giá trị `needs_review`;
  `mode≠label` → warning không có template).
  - `expiry_date`: ngày (`DATE_RE`, nhận cả 和暦 令和/平成/昭和) có `まで有効` ngay sau (cách ≤ 3 ký tự, khác box/dòng cũng được); bỏ ngày
    có `生` theo sau (ngày sinh). Không đọc được `まで有効` → lấy ngày muộn nhất, `needs_review` + note.
  - `issuer`: `ISSUER_RE` = cụm kanji/kana kết thúc `市|区|町|村` + `長`, không được có kanji ngay sau (loại địa chỉ kiểu `千代田区長田町`);
    lấy match **cuối** vì nơi cấp in dưới địa chỉ.
  - Quality: đếm 4 chữ in (`個人番号カード`, `氏名`, `住所`, `まで有効`). `cross_check`: thẻ hết hạn → warning; hạn > 10 năm kể từ hôm nay
    → `needs_review` (thẻ cấp tối đa 10 năm).
  - Test: box viết tay (`tests/test_my_number_card.py`) + OCR ảnh mẫu chính thức (xem dưới). Chưa thử ảnh chụp thẻ thật.
    Layout thẻ mẫu mới 2026 (次期マイナンバーカード) chưa kiểm; tiêu đề nhận cả `マイナンバーカード`.
- `driver_license/` (運転免許証, `document_type=driver_license`): `license_number` = 12 chữ số trong `第 … 号` (OCR tách số bằng dấu cách,
  sửa O/I/S… → số, có sửa thì note); không thấy `第…号` → dãy 12 chữ số bất kỳ + note. Kiểm tra: 2 số đầu ∈ `COMMISSION_CODES` (mã 公安委員会;
  Hokkaido 10–14). Warning "không phải bằng lái" chỉ khi không thấy cả `運転免許証` lẫn `公安委員会` (`運転免許証` in dọc cạnh ảnh, OCR hay bỏ sót).
  Không kiểm check digit (số thứ 11) vì chưa xác minh được thuật toán. `issue_date` = ngày ngay sau `交付` (≤ 4 ký tự);
  không đọc được `交付` → nếu chỉ còn đúng 1 ngày không phải ngày sinh (`…生`) / hạn (`…まで有効`, `で` có thể mất) thì lấy + note. Ngày cấp tương lai → `needs_review`.
- `passport/` (hộ chiếu Nhật, chỉ hộ chiếu Nhật theo yêu cầu, `document_type=passport`): `passport_number` từ 2 nguồn: MRZ dòng 2
  (`MRZ2_RE` = 9 ký tự + check digit + `JPN`, bỏ khoảng trắng, `«`/`く`… → `<`) và số in sau nhãn `旅券番号/Passport No.` (≤ 40 ký tự, thường ở
  dòng dưới; bỏ dòng MRZ). Sửa ký tự theo vị trí (2 chữ + 7 số). MRZ đúng check digit (ICAO 7-3-1) → lấy MRZ; số in khác → note. MRZ sai check
  → lấy số in (MRZ khác → note); chỉ có MRZ sai → lấy + note. Không đúng dạng `[A-Z]{2}\d{7}` → `needs_review`. Không thấy 日本国/JAPAN → warning.
- `health_insurance/` (`document_type=health_insurance_card`): `card_type` = tiêu đề (`SCHEMES` 国民健康保険/健康保険/後期高齢者医療/船員保険/共済組合
  + `KINDS` 被保険者証/被扶養者証/資格確認書/組合員証/加入者証, bỏ khoảng trắng). Thiếu phần loại bảo hiểm ngay trước → tìm `SCHEME_RE` trong 40 ký tự trước (tiêu đề in 2 dòng, giữa có
  `有効期限…` như 資格確認書 Nagoya) rồi ghép; không có → note. Thẻ ngừng cấp từ 02/12/2024,
  資格確認書 thay thế cùng bố cục nên nhận cả hai. `insurer_name` = phần còn lại của dòng sau `保険者名称` / `交付者名` / `保険者` (không phải
  `被保険者`, `保険者番号`…), cắt ở nhãn kế tiếp, bỏ dấu `印`; dòng trống → dòng dưới. `issue_date` = ngày sau `交付年月日`/`発行年月日` (≤ 6 ký tự),
  không có → ngày ngay trước `交付` (協会けんぽ in `令和 5年 4月 1日交付`). Ngày cấp tương lai → `needs_review`.
- Ảnh mẫu chính thức (見本, dữ liệu giả) trong `samples/official/` (nguồn + cách cắt: `SOURCES.md`; tải 28/10/2026, tái mã hoá JPEG):
  My Number (TP Kobe), bằng lái (cảnh sát Kanagawa, đã cắt bỏ chú thích), hộ chiếu 2025 + trước 2025 (tỉnh Kanagawa), 国保 資格確認書 (TP Nagoya).
  Kết quả: hộ chiếu 2/2 đúng (MRZ khớp), 資格確認書 3/3 đúng, My Number chỉ hạn thẻ (nơi cấp `□□市長` bị dấu みほん che, OCR không ra chữ),
  bằng lái chỉ số (ảnh 338px: `交付` đọc thành `节`, ngày mất niên hiệu). OCR lưu thành `tests/fixtures/official_*_ocr.json` để test hồi quy.
  Chưa thử ảnh chụp giấy tờ thật.
- `static/`: UI HTML/JS thuần. Chọn ảnh (chọn file, kéo thả, dán, camera) chỉ xem trước (`selectFile`), **không tự gửi**: người dùng chọn
  giấy tờ (mặc định "Tự nhận diện" = `auto`, trạng thái ghi loại đã nhận) /tuỳ chọn rồi bấm "Nhận dạng" (`#submit` → `upload(selectedFile)`); ảnh giữ lại để đổi tuỳ chọn và chạy lại (yêu cầu 28/10/2026).
  "Chạy lại trực tiếp" ở tab mẫu vẫn chạy ngay (mẫu đã có `document`). (chọn loại giấy tờ `document`, nhớ trong localStorage; engine VL khoá chọn `mode`; chọn `mode`, vẽ `zones_px`
  khi bật "Hiện ô template"; tên trường hiển thị theo `document_type`). Nút "Chụp ảnh bằng camera": `getUserMedia` (camera sau, xin
  độ phân giải tối đa, khung ngắm tỉ lệ ID-1, chụp ra JPEG rồi đi qua cùng luồng upload); chỉ chạy ở secure context (https/localhost) →
  mở từ điện thoại qua `http://<IP LAN>` thì rơi về `<input capture="environment">` (mở app camera của máy). Tab "Mẫu chính thức":
  `static/samples/results.json`, mỗi mẫu có nguồn riêng, "Chạy lại" đặt luôn `document` của mẫu. View "Giấy tờ hỗ trợ" (`docs.js`, nạp trước `app.js`): mỗi loại giấy tờ Nhật = ảnh mẫu chính thức đã xử lý
  (`static/samples/<id>_processed.jpg` của `build_demo`) + ô trường đánh số + bảng trường (danh mục viết tay trong `docs.js`, ví dụ =
  `results.json` theo `sample` id). Ô: thẻ cư trú lấy từ `/api/zones` (template mode zone); loại khác không có template → `boxes`
  (toạ độ 0–1 trên ảnh đã xử lý, đo từ khung OCR của chính ảnh mẫu; nơi cấp My Number đo tay vì OCR không đọc được; 1 trường có thể
  nhiều ô, vd số hộ chiếu + MRZ). Tỉ lệ khung = `template.aspect` hoặc `ocr.image_size` của mẫu. **Thêm/bớt trường hoặc loại giấy tờ
  thì sửa `DOCS` trong `docs.js` và `FIELD_LABELS` trong `app.js`; chạy lại `build_demo` thì kiểm lại `boxes` (ảnh đã xử lý có thể đổi).**
  `main.py` gắn `?v=mtime` cho `app.js`, `docs.js`, `style.css`. Tab "Luồng xử lý" (`#view-guide`, HTML tĩnh trong `index.html`,
  viết 28/10/2026 thay `how-it-works.html` + `design.html` đã xoá): đầu vào, xử lý ảnh lớn/nhỏ, xoay, cắt viền, OCR + gom dòng, nhận diện loại,
  theo nhãn, theo vị trí/kết hợp, kiểm tra, JSON, giới hạn; ảnh minh hoạ thật trong `static/howto/` (`scripts/build_howto.py`).
  **Đổi luồng xử lý, ngưỡng, dấu hiệu nhận diện hay cách đọc của loại giấy tờ nào thì cập nhật tab này** (các con số trong đó lấy từ code).

### vl_service/ (PaddleOCR-VL, cổng 8011)
- Tách riêng vì VL cần paddlepaddle 3.3.x, bản này crash PP-OCRv5 trên CPU (oneDNN). App chính pin 3.2.2.
- **Quyết định: chạy native trên host, không đưa vào Docker** (dù có `vl_service/Dockerfile`). Lý do: máy dev là Mac M4
  16GB, container phải chạy amd64 qua Rosetta (chậm hơn), và VL trên CPU nạp weight float32 cần > 8GB RAM cho Docker.
  Chạy (Python 3.10, `.venv` có sẵn), log luôn ghi vào `logs/vl_service.log` trong project (không để ở thư mục tạm):
  `cd vl_service && .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8011 >> ../logs/vl_service.log 2>&1`
- Mode `layout` (block có bbox) hoặc `whole` (không bbox).
- `vl_probe.py <ảnh> [pipeline_version]`: dev-only, in format/tốc độ output PaddleOCR-VL (chạy bằng `.venv` của vl_service).
- `VL_DEVICE` truyền vào `PaddleOCRVL(device=)`; `/health` trả `device`.
- `.dockerignore` của app loại `vl_service/` và mọi `.venv` (venv VL ~1.1GB, trước đây bị gửi vào build context).

### deploy/aws-ec2-gpu/ (server GPU, không Docker)
- `install.sh` (chạy bằng sudo trong bản clone repo, Ubuntu 24.04 + Deep Learning Base GPU AMI có sẵn driver NVIDIA; g6.xlarge = L4):
  tạo `.venv` + `vl_service/.venv` bằng python3.12, cài `paddlepaddle-gpu` **cùng version pin trong requirements** từ index Paddle
  (`PADDLE_CUDA=cu126`; GPU wheel không có trên PyPI, CUDA/cuDNN đi kèm dạng pip `nvidia-*`), gỡ `paddlepaddle` CPU nếu có, chạy
  `paddle.utils.run_check()`, tải model, ghi `/etc/ocr/{ocr,vl}.env` (chỉ khi chưa có; mặc định `*_DEVICE=gpu:0`, tắt log PII),
  service systemd `ocr-app` (8000, `APP_HOST` mặc định 127.0.0.1) + `ocr-vl` (127.0.0.1:8011), log ra `logs/app.log`,
  `logs/vl_service.log`; `DOMAIN` → Caddy HTTPS (Let's Encrypt, camera trong trang cần secure context), `BASIC_AUTH_*` → mật khẩu
  (API không có auth). Cuối script gọi health, cảnh báo nếu `device` không phải GPU. Chạy lại được (cập nhật sau `git pull`).
  Chưa chạy thử trên EC2 thật (viết 28/10/2026). Hướng dẫn: `deploy/aws-ec2-gpu/README.md`. Đổi requirements/env/service → sửa cả 2 file.

### scripts/, tests/
- `make_sample.py` sinh thẻ giả; `build_demo.py` chạy pipeline trên mọi ảnh mẫu chính thức (`SAMPLES`: `src`, `document`, nguồn từng ảnh)
  → `static/samples/` (ảnh + `results.json`, tab "Mẫu chính thức" và ví dụ trong tab "Giấy tờ hỗ trợ"); `build_howto.py` đặt thẻ mẫu ISA
  vào ảnh giả lập (ảnh chụp sát `closeup_tilt` cắt mất 2 ký tự cuối số thẻ → số thẻ sai nhưng bị gắn cờ, đúng như mong đợi) (xiên, nền cùng màu, chụp sát nghiêng), chạy pipeline thật, ghi ảnh + `summary.json` vào `static/howto`; `download_models.py` tải model khi build.
- `test_detect.py`: nhận diện trên OCR ảnh mẫu chính thức, không nhận ra / không chắc, chữ giản thể; `pipeline.extract(document="auto")` với
  `_ocr`/`normalize_card` giả (hộ chiếu OCR lại ảnh gốc, `UnknownDocument`).
- `test_jp_documents.py`: bằng lái, hộ chiếu (MRZ đúng/sai check digit, `«` thay `<`), bảo hiểm (協会けんぽ, 国保 với `R5. 4. 1`, 資格確認書),
  `jp_residence` chỉ trả `card_number`, hộ chiếu không cắt thẻ; OCR thật của ảnh mẫu chính thức (`official_*_ocr.json`).
- `test_my_number_card.py`: thẻ My Number trên box viết tay (nơi cấp kana, địa chỉ chứa `区長`, thiếu `まで有効`, kiểm tra chéo hạn thẻ).
- `test_zones.py`: mode zone/hybrid trên fixture (trùng mode nhãn, thẻ nhỏ + nghiêng, mất nhãn, < 3 mốc, crop).
- `test_preprocess.py`: ảnh tổng hợp bằng OpenCV (thẻ nhạt màu nghiêng, bị che góc; ảnh đã cắt sát) + `estimate_skew`/`rotate`.
- Test parser dùng OCR fixture (`tests/fixtures/*.json`, đọc qua `parse_fixture`) hoặc box viết tay, không cần Paddle; `test_vl_client.py`
  dựng HTTP server giả thay cho vl_service.
