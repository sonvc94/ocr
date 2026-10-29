"""Run the full pipeline on official specimen documents (見本) and store the results for the "Mẫu chính thức" tab.

Sources: residence cards from the Immigration Services Agency (ISA, samples/isa/), the other documents from
Japanese government / municipal pages (samples/official/, see samples/official/SOURCES.md).

Usage (inside the container, with app/static mounted so the output lands in the repo):
    docker compose run --rm -v ./app/static:/app/app/static app python -m scripts.build_demo
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from app import pipeline
from app.preprocess import encode_jpeg, load_image

ISA = {
    "source_name": "Cục Xuất nhập cảnh (ISA)",
    "source_page": "https://www.moj.go.jp/isa/applications/procedures/whatzairyu_00001.html",
    "source_pdf": "https://www.moj.go.jp/isa/content/001465339.pdf",
}
ISA_SPRC = {
    "source_name": "Cục Xuất nhập cảnh (ISA)",
    "source_page": "https://www.moj.go.jp/isa/applications/procedures/tetuduki_tokubetu_shomeisho_00001.html",
    "source_pdf": "https://www.moj.go.jp/isa/content/001465342.pdf",
}

SAMPLES = [
    ISA | {
        "id": "residence_card_current",
        "src": "samples/isa/residence_card_current.jpg",
        "document": "jp_residence",
        "title": "Residence Card (在留カード) — 2012 design (issued until 2026-06-13)",
        "description": "Thẻ mẫu chính thức (見本) mẫu cũ, ảnh gốc 509×320px trích từ tờ hướng dẫn của Cục Xuất nhập cảnh. API chỉ trả số thẻ.",
    },
    ISA | {
        "id": "residence_card_new_2026",
        "src": "samples/isa/residence_card_new_2026.jpg",
        "document": "jp_residence",
        "title": "Residence Card (在留カード) — 2026 design (issued from 2026-06-14)",
        "description": "Mẫu mới in số thẻ ở phía dưới. Ảnh gốc 665×416px. API chỉ trả số thẻ.",
    },
    ISA | {
        "id": "specified_residence_card_2026",
        "src": "samples/isa/specified_residence_card_2026.jpg",
        "document": "jp_residence",
        "title": "Specified Residence Card (特定在留カード) — combined with My Number (from 2026-06-14)",
        "description": "Bố cục khác hoàn toàn, demo CHƯA hỗ trợ — đưa vào để thấy hệ thống cảnh báo thay vì trả kết quả sai một cách im lặng.",
    },
    {
        "id": "my_number_card",
        "src": "samples/official/my_number_card.jpg",
        "document": "jp_mynumber",
        "title": "My Number Card (マイナンバーカード)",
        "description": "Ảnh mẫu 507×317px. Nơi cấp in là 「□□市長」 (chữ giữ chỗ) và bị dấu みほん đè lên nên OCR không đọc được; hạn thẻ đọc đúng.",
        "source_name": "Thành phố Kobe (神戸市)",
        "source_page": "https://www.city.kobe.lg.jp/a53715/mynumbercard.html",
    },
    {
        "id": "driver_license",
        "src": "samples/official/driver_license.jpg",
        "document": "jp_driver_license",
        "title": "Driver's License (運転免許証)",
        "description": "Ảnh mẫu rất nhỏ (cắt phần thẻ, 338×225px, bỏ chú thích bên phải): đọc được License number, chữ 交付 và niên hiệu của ngày cấp bị đọc sai nên không lấy được ngày cấp.",
        "source_name": "Cảnh sát tỉnh Kanagawa (神奈川県警察)",
        "source_page": "https://www.police.pref.kanagawa.jp/tetsuzuki/menkyo/mes83080.html",
    },
    {
        "id": "passport_2025",
        "src": "samples/official/passport_2025.jpg",
        "document": "jp_passport",
        "title": "Japanese Passport (旅券) — 2025 design (applications from 2025-03-24)",
        "description": "Trang thông tin cá nhân, ảnh 800×538px. Số in trên trang và số trong MRZ (đúng check digit) khớp nhau.",
        "source_name": "Tỉnh Kanagawa (神奈川県)",
        "source_page": "https://www.pref.kanagawa.jp/docs/h6d/passport/aboutpass.html",
    },
    {
        "id": "passport_2020",
        "src": "samples/official/passport_2020.jpg",
        "document": "jp_passport",
        "title": "Japanese Passport (旅券) — design before 2025",
        "description": "Trang thông tin cá nhân, ảnh 800×512px.",
        "source_name": "Tỉnh Kanagawa (神奈川県)",
        "source_page": "https://www.pref.kanagawa.jp/docs/h6d/passport/aboutpass.html",
    },
    {
        "id": "health_insurance_shikaku_kakuninsho",
        "src": "samples/official/health_insurance_shikaku_kakuninsho.jpg",
        "document": "jp_health_insurance",
        "title": "Health Insurance Card — National Health Insurance 資格確認書 (国民健康保険)",
        "description": "Mẫu cho người dưới 70 tuổi của bảo hiểm y tế quốc dân, ảnh 752×469px. Đơn vị cấp in ở 交付者名.",
        "source_name": "Thành phố Nagoya (名古屋市)",
        "source_page": "https://www.city.nagoya.jp/kurashi/hoken/1011736/1011750/1011753.html",
    },    ISA_SPRC | {
        "id": "special_permanent_resident",
        "src": "samples/official/special_permanent_resident.jpg",
        "document": "jp_special_permanent",
        "title": "Special Permanent Resident Certificate (特別永住者証明書) — current design (issued until 2026-06-13)",
        "description": "Ảnh mẫu 522×332px cắt từ tờ hướng dẫn của Cục Xuất nhập cảnh. Lấy số giấy chứng nhận và hạn.",
    },
    ISA_SPRC | {
        "id": "special_permanent_resident_2026",
        "src": "samples/official/special_permanent_resident_2026.jpg",
        "document": "jp_special_permanent",
        "title": "Special Permanent Resident Certificate (特別永住者証明書) — 2026 design (issued from 2026-06-14)",
        "description": "Mẫu mới in số ở dải phía dưới, ảnh 684×436px cùng tờ hướng dẫn.",
    },
    {
        "id": "driving_history",
        "src": "samples/official/driving_history.jpg",
        "document": "jp_driving_history",
        "title": "Driving History Certificate (運転経歴証明書)",
        "description": "Hình minh hoạ mẫu mới (vẽ từ PDF, cắt mặt trước). Cùng mẫu với Driver's License: License number đã trả lại (第…号) và ngày cấp (交付).",
        "source_name": "Tỉnh Okayama (岡山県)",
        "source_page": "https://www.pref.okayama.jp/uploaded/life/963605_9262306_misc.pdf",
    },
    {
        "id": "juki_card",
        "src": "samples/official/juki_card.jpg",
        "document": "jp_juki_card",
        "title": "Basic Resident Register Card (住民基本台帳カード) — photo type",
        "description": "Sơ đồ mẫu thẻ của Bộ Nội vụ (vẽ từ PDF, khung ảnh để trống); nơi cấp là chữ giữ chỗ △△市. Thẻ ngừng cấp 12/2015, mọi thẻ đã hết hạn.",
        "source_name": "Bộ Nội vụ và Truyền thông (総務省)",
        "source_page": "https://www.soumu.go.jp/main_sosiki/kenkyu/kouteki_kojin/pdf/080916_1_si7.pdf",
    },
    {
        "id": "resident_record",
        "src": "samples/official/resident_record.jpg",
        "document": "jp_resident_record",
        "title": "Resident Record (住民票の写し) — full page",
        "description": "Mẫu bố cục chuẩn từ 26/05/2025, ảnh 760×1083px. Địa chỉ đọc được; ngày chứng nhận là chữ giữ chỗ (令和●年●月●●日) nên không lấy. "
                       "Số My Number trên mẫu đã ghi 【省略】; nếu có số thật sẽ bị che.",
        "source_name": "Thành phố Kobe (神戸市)",
        "source_page": "https://www.city.kobe.lg.jp/a53715/20250507_system-std.html",
    },
    {
        "id": "pension_notice",
        "src": "samples/official/pension_notice.jpg",
        "document": "jp_pension_book",
        "title": "National Pension Handbook — Basic Pension Number Notice (基礎年金番号通知書, replaces 年金手帳)",
        "description": "Hình minh hoạ: số in là XXXX-XXXXXX, ngày cấp 令和X年X月X日 (chữ giữ chỗ) nên không có giá trị nào để lấy — đúng là không bịa ra số.",
        "source_name": "Bộ Y tế, Lao động và Phúc lợi / Cơ quan Hưu trí Nhật (厚生労働省・日本年金機構)",
        "source_page": "https://www.city.adachi.tokyo.jp/koreiryo/kurashi/hoken/nenkin-oshirase20220218.html",
    },
]


def main() -> None:
    out_dir = Path("app/static/samples")
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for sample in SAMPLES:
        src = Path(sample["src"])
        shutil.copy(src, out_dir / src.name)
        img, original_size = load_image(src.read_bytes())
        result, img = pipeline.extract(img, original_size, document=sample["document"])
        processed = out_dir / f"{sample['id']}_processed.jpg"
        processed.write_bytes(encode_jpeg(img))
        results.append(
            sample
            | {
                "image": f"/static/samples/{src.name}",
                "processed_image": f"/static/samples/{processed.name}",
                "result": result,
            }
        )
        found = sum(f["value"] is not None for f in result["fields"].values())
        print(f"{sample['id']}: design={result['card_design']} quality={result['quality']['level']} found={found}")
    generated = time.strftime("%Y-%m-%d")
    (out_dir / "results.json").write_text(
        json.dumps({"generated": generated, "samples": results}, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
