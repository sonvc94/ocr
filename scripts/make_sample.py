"""Render a synthetic residence-card front with fake data, for testing without real customer images.

The layout only approximates the real card; it is good enough to exercise OCR + parsing.
Usage: python -m scripts.make_sample --font /path/to/japanese.ttc --out samples/synthetic.jpg [--photo]
"""

from __future__ import annotations

import argparse
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1600, 1009

FAKE = {
    "number": "AB12345678CD",
    "name": "NGUYEN VAN AN",
    "dob": "1995年04月12日",
    "sex": "男 M.",
    "nationality": "ベトナム",
    "address": "東京都新宿区西新宿二丁目8番1号 サンプルマンション101号室",
    "status": "技術・人文知識・国際業務",
    "work": "在留資格に基づく就労活動のみ可",
    "period": "5年 (2029年06月30日)",
    "permission": "在留期間更新許可 (東京出入国在留管理局長)",
    "permitted": "2024年06月20日",
    "issued": "2024年06月30日",
    "valid": "2029年06月30日",
}


def render(font_path: str) -> Image.Image:
    img = Image.new("RGB", (W, H), (236, 241, 238))
    d = ImageDraw.Draw(img)
    # light guilloche-ish background pattern, like the real card's security print
    for i in range(0, W + H, 18):
        d.line([(i, 0), (i - H, H)], fill=(222, 232, 228), width=2)

    def f(size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(font_path, size)

    label, small, value, big = f(30), f(20), f(38), f(52)
    gray, black = (90, 100, 105), (20, 20, 20)

    d.text((60, 40), "在留カード", font=big, fill=black)
    d.text((60, 102), "RESIDENCE CARD", font=small, fill=gray)
    d.text((980, 50), "番号", font=label, fill=gray)
    d.text((1060, 44), FAKE["number"], font=value, fill=black)

    def row(y: int, jp: str, en: str, val: str, x_val: int = 260, font=value):
        d.text((60, y), jp, font=label, fill=gray)
        d.text((60, y + 34), en, font=small, fill=gray)
        d.text((x_val, y - 4), val, font=font, fill=black)

    row(160, "氏名", "NAME", FAKE["name"], font=big)
    row(250, "生年月日", "DATE OF BIRTH", FAKE["dob"])
    d.text((640, 250), "性別", font=label, fill=gray)
    d.text((720, 246), FAKE["sex"], font=value, fill=black)
    d.text((860, 250), "国籍・地域", font=label, fill=gray)
    d.text((1020, 246), FAKE["nationality"], font=value, fill=black)
    row(340, "住居地", "ADDRESS", FAKE["address"], font=f(34))
    row(440, "在留資格", "STATUS", FAKE["status"], font=big)
    row(540, "就労制限の有無", "", FAKE["work"], x_val=320)
    row(620, "在留期間(満了日)", "PERIOD OF STAY", FAKE["period"], x_val=360)
    row(710, "許可の種類", "TYPE OF PERMISSION", FAKE["permission"], x_val=300, font=f(34))
    row(800, "許可年月日", "DATE OF PERMISSION", FAKE["permitted"], x_val=300)
    d.text((760, 800), "交付年月日", font=label, fill=gray)
    d.text((930, 796), FAKE["issued"], font=value, fill=black)
    d.text((60, 900), f"このカードは {FAKE['valid']} まで有効 です。", font=value, fill=(160, 30, 30))

    # photo placeholder + watermark
    d.rectangle([1230, 160, 1540, 560], fill=(200, 205, 210), outline=gray, width=3)
    d.text((1310, 340), "PHOTO", font=label, fill=gray)
    d.text((1180, 900), "SAMPLE", font=big, fill=(200, 60, 60))
    return img


def as_photo(card: Image.Image) -> Image.Image:
    """Place the card on a darker background with perspective skew and blur, like a phone photo."""
    bg = Image.new("RGB", (2200, 1700), (70, 66, 60))
    bg.paste(card, (300, 340))
    skew = (1.0, 0.04, -120, -0.03, 1.0, 40, 0.00004, 0.00002)
    out = bg.transform(bg.size, Image.Transform.PERSPECTIVE, skew, Image.Resampling.BICUBIC, fillcolor=(70, 66, 60))
    out = out.filter(ImageFilter.GaussianBlur(1.2))
    random.seed(0)
    px = out.load()
    for _ in range(40000):
        x, y = random.randrange(out.width), random.randrange(out.height)
        r, g, b = px[x, y]
        n = random.randint(-25, 25)
        px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", required=True)
    ap.add_argument("--out", default="samples/synthetic.jpg")
    ap.add_argument("--photo", action="store_true", help="simulate a skewed, noisy phone photo")
    args = ap.parse_args()
    img = render(args.font)
    if args.photo:
        img = as_photo(img)
    img.save(args.out, quality=90)
    print("wrote", args.out)
