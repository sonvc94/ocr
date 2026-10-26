"""Run the full pipeline on the official ISA specimen cards and store the results for the "Mẫu chính thức" tab.

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

SOURCE_PAGE = "https://www.moj.go.jp/isa/applications/procedures/whatzairyu_00001.html"
SOURCE_PDF = "https://www.moj.go.jp/isa/content/001465339.pdf"

SAMPLES = [
    {
        "id": "residence_card_current",
        "title": "在留カード — mẫu hiện hành (cấp đến 13/06/2026)",
        "description": "Thẻ mẫu chính thức (見本) mẫu cũ, ảnh gốc 509×320px trích từ tờ hướng dẫn của Cục Xuất nhập cảnh.",
    },
    {
        "id": "residence_card_new_2026",
        "title": "在留カード — mẫu mới (cấp từ 14/06/2026)",
        "description": "Mẫu mới không còn in thời hạn lưu trú, loại/ngày cấp phép và ngày cấp thẻ (chỉ lưu trong chip IC). Ảnh gốc 665×416px.",
    },
    {
        "id": "specified_residence_card_2026",
        "title": "特定在留カード — thẻ cư trú gộp My Number (từ 14/06/2026)",
        "description": "Bố cục khác hoàn toàn, demo CHƯA hỗ trợ — đưa vào để thấy hệ thống cảnh báo thay vì trả kết quả sai một cách im lặng.",
    },
]


def main() -> None:
    src_dir = Path("samples/isa")
    out_dir = Path("app/static/samples")
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for sample in SAMPLES:
        src = src_dir / f"{sample['id']}.jpg"
        shutil.copy(src, out_dir / src.name)
        img, original_size = load_image(src.read_bytes())
        result, img = pipeline.extract(img, original_size)
        processed = out_dir / f"{sample['id']}_processed.jpg"
        processed.write_bytes(encode_jpeg(img))
        results.append(
            sample
            | {
                "image": f"/static/samples/{src.name}",
                "processed_image": f"/static/samples/{processed.name}",
                "source_page": SOURCE_PAGE,
                "source_pdf": SOURCE_PDF,
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
