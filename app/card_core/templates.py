"""Where things are printed on each card design (`<card package>/data/templates.json`).

Coordinates are relative to the card (0–1 from its top-left corner): `[x0, y0, x1, y1]`, measured on a
specimen image; `anchors` are single OCR lines (labels, titles) used to locate the card in a photo.
"""

from __future__ import annotations

import json
from pathlib import Path


# Card pixel space the relative coordinates are scaled to, so that x and y share one unit
# (needed for a rotation + uniform scale fit). Same size preprocess.normalize_card warps to.
CARD_W = 1600.0


def load_templates(path: Path) -> dict[str, dict]:
    """card design -> template."""
    return json.loads(path.read_text(encoding="utf-8"))


def card_h(template: dict) -> float:
    return CARD_W / template["aspect"]


def to_card_px(template: dict, box: list[float]) -> tuple[float, float, float, float]:
    h = card_h(template)
    return box[0] * CARD_W, box[1] * h, box[2] * CARD_W, box[3] * h
