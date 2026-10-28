"""Render a synthetic Vietnamese identity card front (thẻ căn cước, 2024 design) with fake data.

Values are printed onto the official specimen image (samples/vn/can_cuoc_2024_specimen.jpg, which has empty
fields), at the positions of app/vn_id_card/data/templates.json. The fake numbers follow the real rules
(province code, sex/century digit, birth year), so cross-checks pass.
Usage (font with Vietnamese glyphs, e.g. Arial Bold from macOS mounted at /fonts):
  python -m scripts.make_sample_vn --font "/fonts/Arial Bold.ttf" --person 0 --out samples/vn/synthetic_0.jpg [--photo]
"""

from __future__ import annotations

import argparse

from PIL import Image, ImageDraw, ImageFont

from scripts.make_sample import as_photo

SPECIMEN = "samples/vn/can_cuoc_2024_specimen.jpg"
W, H = 1600, 1009  # ID-1 aspect, the size preprocess.normalize_card warps to

PEOPLE = [
    # 001 Hà Nội, 1 = female born 1900s, 95 = 1995; issued 2024 at 29 -> valid until the 40th birthday
    {"number": "001195012345", "name": "NGUYỄN THỊ THU HƯƠNG", "dob": "12/04/1995", "sex": "Nữ", "expiry": "12/04/2035"},
    # 079 TP. Hồ Chí Minh, 2 = male born 2000s, 03 = 2003; issued at 20 -> valid until the 25th birthday
    {"number": "079203004567", "name": "TRẦN ĐỨC ANH", "dob": "05/11/2003", "sex": "Nam", "expiry": "05/11/2028"},
]


def render(font_path: str, person: dict) -> Image.Image:
    img = Image.open(SPECIMEN).convert("RGB").resize((W, H), Image.Resampling.LANCZOS)
    d = ImageDraw.Draw(img)
    black = (25, 25, 30)

    def text(x: int, y: int, value: str, size: int) -> None:
        d.text((x, y), value, font=ImageFont.truetype(font_path, size), fill=black, anchor="ls")  # y = baseline

    text(980, 482, person["number"], 50)
    text(480, 712, person["name"], 52)
    text(1115, 822, person["dob"], 42)
    text(745, 935, person["sex"], 42)
    text(1265, 935, "Việt Nam", 42)
    text(60, 985, person["expiry"], 38)
    return img


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", required=True)
    ap.add_argument("--person", type=int, default=0, choices=range(len(PEOPLE)))
    ap.add_argument("--out", default="samples/vn/synthetic_0.jpg")
    ap.add_argument("--photo", action="store_true", help="simulate a skewed, noisy phone photo")
    args = ap.parse_args()
    img = render(args.font, PEOPLE[args.person])
    if args.photo:
        img = as_photo(img)
    img.save(args.out, quality=90)
    print("wrote", args.out)
