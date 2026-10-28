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

SAMPLES = [
    ISA | {
        "id": "residence_card_current",
        "src": "samples/isa/residence_card_current.jpg",
        "document": "jp_residence",
        "title": "在留カード — mẫu hiện hành (cấp đến 13/06/2026)",
        "description": "Thẻ mẫu chính thức (見本) mẫu cũ, ảnh gốc 509×320px trích từ tờ hướng dẫn của Cục Xuất nhập cảnh. API chỉ trả số thẻ.",
    },
    ISA | {
        "id": "residence_card_new_2026",
        "src": "samples/isa/residence_card_new_2026.jpg",
        "document": "jp_residence",
        "title": "在留カード — mẫu mới (cấp từ 14/06/2026)",
        "description": "Mẫu mới in số thẻ ở phía dưới. Ảnh gốc 665×416px. API chỉ trả số thẻ.",
    },
    ISA | {
        "id": "specified_residence_card_2026",
        "src": "samples/isa/specified_residence_card_2026.jpg",
        "document": "jp_residence",
        "title": "特定在留カード — thẻ cư trú gộp My Number (từ 14/06/2026)",
        "description": "Bố cục khác hoàn toàn, demo CHƯA hỗ trợ — đưa vào để thấy hệ thống cảnh báo thay vì trả kết quả sai một cách im lặng.",
    },
    {
        "id": "my_number_card",
        "src": "samples/official/my_number_card.jpg",
        "document": "jp_mynumber",
        "title": "マイナンバーカード — thẻ My Number",
        "description": "Ảnh mẫu 507×317px. Nơi cấp in là 「□□市長」 (chữ giữ chỗ) và bị dấu みほん đè lên nên OCR không đọc được; hạn thẻ đọc đúng.",
        "source_name": "Thành phố Kobe (神戸市)",
        "source_page": "https://www.city.kobe.lg.jp/a53715/mynumbercard.html",
    },
    {
        "id": "driver_license",
        "src": "samples/official/driver_license.jpg",
        "document": "jp_driver_license",
        "title": "運転免許証 — bằng lái xe",
        "description": "Ảnh mẫu rất nhỏ (cắt phần thẻ, 338×225px, bỏ chú thích bên phải): đọc được số bằng lái, chữ 交付 và niên hiệu của ngày cấp bị đọc sai nên không lấy được ngày cấp.",
        "source_name": "Cảnh sát tỉnh Kanagawa (神奈川県警察)",
        "source_page": "https://www.police.pref.kanagawa.jp/tetsuzuki/menkyo/mes83080.html",
    },
    {
        "id": "passport_2025",
        "src": "samples/official/passport_2025.jpg",
        "document": "jp_passport",
        "title": "旅券 — hộ chiếu mẫu 2025 (nộp đơn từ 24/03/2025)",
        "description": "Trang thông tin cá nhân, ảnh 800×538px. Số in trên trang và số trong MRZ (đúng check digit) khớp nhau.",
        "source_name": "Tỉnh Kanagawa (神奈川県)",
        "source_page": "https://www.pref.kanagawa.jp/docs/h6d/passport/aboutpass.html",
    },
    {
        "id": "passport_2020",
        "src": "samples/official/passport_2020.jpg",
        "document": "jp_passport",
        "title": "旅券 — hộ chiếu mẫu trước 2025",
        "description": "Trang thông tin cá nhân, ảnh 800×512px.",
        "source_name": "Tỉnh Kanagawa (神奈川県)",
        "source_page": "https://www.pref.kanagawa.jp/docs/h6d/passport/aboutpass.html",
    },
    {
        "id": "health_insurance_shikaku_kakuninsho",
        "src": "samples/official/health_insurance_shikaku_kakuninsho.jpg",
        "document": "jp_health_insurance",
        "title": "国民健康保険 資格確認書 — thay thẻ bảo hiểm y tế",
        "description": "Mẫu cho người dưới 70 tuổi của bảo hiểm y tế quốc dân, ảnh 752×469px. Đơn vị cấp in ở 交付者名.",
        "source_name": "Thành phố Nagoya (名古屋市)",
        "source_page": "https://www.city.nagoya.jp/kurashi/hoken/1011736/1011750/1011753.html",
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
