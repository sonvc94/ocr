"""Build the step-by-step images for the "Luồng xử lý" tab (static/index.html, section 4) from the ISA specimen card.

Each case places the specimen in a simulated photo (tilted / perspective / low-contrast background),
runs the real pipeline and saves: the photo, the processed image with OCR boxes, and a summary JSON.

    docker compose run --rm -v ./app/static:/app/app/static app python -m scripts.build_howto
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from app.pipeline import extract

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
OUT = STATIC / "howto"
CARD = STATIC / "samples" / "residence_card_current.jpg"


def _background(w: int, h: int, color: tuple[int, int, int], seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    bg = np.full((h, w, 3), color, np.float32)
    gradient = np.linspace(-25, 25, w, dtype=np.float32)[None, :, None]
    bg += gradient + rng.normal(0, 6, (h, w, 3))
    return bg.clip(0, 255).astype(np.uint8)


def _place(card: np.ndarray, bg: np.ndarray, quad: list[tuple[int, int]]) -> np.ndarray:
    h, w = card.shape[:2]
    src = np.float32([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]])
    m = cv2.getPerspectiveTransform(src, np.float32(quad))
    warped = cv2.warpPerspective(card, m, (bg.shape[1], bg.shape[0]))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, (bg.shape[1], bg.shape[0]))
    out = bg.copy()
    out[mask > 0] = warped[mask > 0]
    return out


def _rotated_quad(cx: float, cy: float, w: float, h: float, deg: float) -> list[tuple[int, int]]:
    r = np.radians(deg)
    pts = np.array([[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]])
    rot = np.array([[np.cos(r), -np.sin(r)], [np.sin(r), np.cos(r)]])
    return [(int(x + cx), int(y + cy)) for x, y in pts @ rot.T]


def _draw_boxes(img: np.ndarray, lines: list[dict]) -> np.ndarray:
    out = img.copy()
    for line in lines:
        x1, y1, x2, y2 = (int(v) for v in line["box"])
        color = (40, 170, 40) if line["score"] >= 0.85 else (40, 40, 220)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 3)
    return out


def _save(path: Path, img: np.ndarray, width: int = 900) -> None:
    h, w = img.shape[:2]
    img = cv2.resize(img, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, 82])


def main() -> None:
    OUT.mkdir(exist_ok=True)
    card = cv2.imread(str(CARD))
    card_color = tuple(int(c) for c in card.reshape(-1, 3).mean(axis=0))
    cases = {
        # card small on a dark table, shot at an angle
        "perspective": _place(card, _background(1600, 1200, (70, 60, 55), 1),
                              [(420, 300), (1230, 360), (1190, 880), (360, 800)]),
        # card on a background of almost the same colour, slightly rotated: edges are hard to see
        "low_contrast_tilt": _place(card, _background(1600, 1200, card_color, 2),
                                    _rotated_quad(800, 600, 1150, 725, 8)),
        # close-up, tilted, card corners outside the frame: no card edge to find, the text tilt is used instead
        "closeup_tilt": _place(card, _background(1600, 1150, card_color, 3),
                               _rotated_quad(800, 575, 1660, 1047, 6)),
    }
    summary = {}
    for name, photo in cases.items():
        result, processed = extract(photo, (photo.shape[1], photo.shape[0]))
        _save(OUT / f"{name}_1_photo.jpg", photo)
        _save(OUT / f"{name}_2_processed.jpg", processed)
        _save(OUT / f"{name}_3_boxes.jpg", _draw_boxes(processed, result["ocr"]["lines"]))
        summary[name] = {
            "card_cropped": result["ocr"]["card_cropped"],
            "deskew_deg": result["ocr"]["deskew_deg"],
            "lines": len(result["ocr"]["lines"]),
            "quality": result["quality"]["level"],
            "fields": {k: {"value": f["value"], "needs_review": f["needs_review"]} for k, f in result["fields"].items()},
        }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
