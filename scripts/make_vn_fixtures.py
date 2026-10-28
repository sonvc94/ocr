"""Dev-only: OCR images with the Vietnamese model and save the lines as test fixtures (tests/fixtures/vn_<name>_ocr.json).

Usage (inside the container, with tests/ mounted): python -m scripts.make_vn_fixtures samples/vn/synthetic_0.jpg ...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.ocr.ppocr import run_ocr
from app.preprocess import load_image, normalize_card

if __name__ == "__main__":
    for src in sys.argv[1:]:
        img, _ = load_image(Path(src).read_bytes())
        img, cropped = normalize_card(img)
        boxes, img, _ = run_ocr(img, "vi")
        out = Path("tests/fixtures") / f"vn_{Path(src).stem}_ocr.json"
        lines = [{"text": b.text, "score": round(b.score, 4), "box": [round(v, 1) for v in b.box]} for b in boxes]
        out.write_text(json.dumps({"image_size": [img.shape[1], img.shape[0]], "cropped": cropped, "lines": lines}, ensure_ascii=False, indent=1))
        print("wrote", out)
