"""Field values by position (mode=zone/hybrid): OCR text falling inside a template value box belongs to that field.

Each OCR line is mapped into card coordinates (registration.py). Characters that read as a printed label
are dropped; a line with no readable label whose center lies in a label box is a garbled label, skipped.
A line touching one value box goes to it whole: OCR boxes are often wider than their text, so character
positions are only estimated when they have to be. PP-OCR does return lines spanning several fields
(`1985年12月31日性別女F.国・地域米国`); those are split: each character's x is estimated from character
widths along the line, dates/numbers/Latin words move as one unit, and each unit goes to the value box
it falls in.

The text found per box is then laid out as a small virtual card ("label value" rows) and run through the
same field extraction as label mode (`ZoneSpec.parse`), so cleaning, date parsing and snapping are identical
in both modes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable

import numpy as np

from ..ocr.types import OcrBox
from .field import Field
from .layout import Document
from .registration import Registration
from .templates import CARD_W, card_h

ROW_TOLERANCE = 0.02  # pieces whose centers are this close (card heights) are on the same row
MAX_LINE_HEIGHT = 0.15  # taller "lines" are the photo or a seal


@dataclass(frozen=True)
class ZoneSpec:
    """What zones need to know about a card's print."""

    normalize: Callable[[str], str]
    labels: tuple[re.Pattern, ...]  # printed label text, dropped from lines (searched on normalized text)
    unit: re.Pattern  # kept together when a line is split, so a box edge never cuts a date or a word in two
    markers_only: re.Pattern | None  # a line made only of this is print, not a value (e.g. Y M D under dates)
    label_lang: str  # template label key holding the main label text and box: "jp" -> label.jp / label.jp_box
    parse: Callable[[Document], dict[str, Field]]  # label-mode field extraction, run on the virtual card


def _char_width(c: str) -> float:
    if c.isspace():
        return 0.3
    return 1.0 if unicodedata.east_asian_width(c) in "WF" else 0.55


def _label_mask(text: str, spec: ZoneSpec) -> list[bool]:
    """True for characters that are part of a printed label."""
    mask = [False] * len(text)
    norm = spec.normalize(text)
    if len(norm) != len(text):  # normalization changed the length: positions no longer line up, skip
        return mask
    for pattern in spec.labels:
        for m in pattern.finditer(norm):
            mask[m.start():m.end()] = [True] * (m.end() - m.start())
    return mask


def _inside(x: float, y: float, box: list[float], pad: float = 0.0) -> bool:
    return box[0] - pad <= x <= box[2] + pad and box[1] - pad <= y <= box[3] + pad


def _dist(x: float, box: list[float]) -> float:
    return max(box[0] - x, 0.0, x - box[2])


def _split(text: str, left: float, right: float, mask: list[bool], value_boxes, cy: float, pad: float, unit: re.Pattern) -> dict:
    """Value box -> [(x, unit text)] for a line spanning several value boxes."""
    widths = [_char_width(c) for c in text]
    total = sum(widths) or 1.0
    starts = [0.0]
    for w in widths:
        starts.append(starts[-1] + w)
    out: dict[tuple, list[tuple[float, str]]] = {}
    for m in unit.finditer(text):
        # A unit running on from a label ("NationalityViêt") is placed by its value part only.
        a, b = m.start(), m.end()
        while a < b and mask[a]:
            a += 1
        while b > a and mask[b - 1]:
            b -= 1
        if a == b:
            continue
        x = left + (starts[a] + starts[b]) / 2 / total * (right - left)
        candidates = [vb for vb in value_boxes if _inside(x, cy, vb, pad)]
        if candidates:
            vb = min(candidates, key=lambda v: _dist(x, v))
            out.setdefault(vb, []).append((x, "".join(c for c, lab in zip(text[a:b], mask[a:b]) if not lab)))
    return out


def zone_texts(boxes: list[OcrBox], reg: Registration, template: dict, spec: ZoneSpec) -> dict[tuple, tuple[str, float]]:
    """Value box (as a tuple) -> (text found in it, lowest OCR score of the lines it came from)."""
    pad = template["pad"]
    h = card_h(template)
    value_boxes = {tuple(f["value"]["box"]) for f in template["fields"].values()}
    label_boxes = [b for f in template["fields"].values() if "label" in f for b in (f["label"][f"{spec.label_lang}_box"], f["label"].get("en_box")) if b]
    label_boxes += [f["value"]["en_box"] for f in template["fields"].values() if "en_box" in f["value"]]
    ignore = list(template["ignore"].values())

    pieces: dict[tuple, list[tuple[float, float, str, float]]] = {vb: [] for vb in value_boxes}
    for b in boxes:
        if b.virtual or not b.text.strip() or (spec.markers_only and spec.markers_only.fullmatch(b.text.strip())):
            continue
        card = reg.to_card(np.array([[b.box[0], b.box[1]], [b.box[2], b.box[1]], [b.box[2], b.box[3]], [b.box[0], b.box[3]]]))
        rel = card / [CARD_W, h]
        left, right = (rel[0, 0] + rel[3, 0]) / 2, (rel[1, 0] + rel[2, 0]) / 2
        cy = rel[:, 1].mean()
        if rel[:, 1].max() - rel[:, 1].min() > MAX_LINE_HEIGHT:
            continue
        cx = (left + right) / 2
        if any(_inside(cx, cy, ig) for ig in ignore):
            continue
        mask = _label_mask(b.text, spec)
        # centered on a label box with no label readable in it: a garbled label (a line that does read
        # as a label, e.g. 在留資格留学, keeps its value part)
        if not any(mask) and any(_inside(cx, cy, lb) for lb in label_boxes):
            continue
        touched = [vb for vb in value_boxes if vb[1] - pad <= cy <= vb[3] + pad and left < vb[2] + pad and right > vb[0] - pad]
        if len(set(touched)) == 1:
            units = {touched[0]: [(left, "".join(c for c, lab in zip(b.text, mask) if not lab))]}
        else:
            units = _split(b.text, left, right, mask, value_boxes, cy, pad, spec.unit)
        for vb, us in units.items():
            pieces[vb].append((cy, us[0][0], "".join(u for _, u in us), b.score))

    out = {}
    for vb, ps in pieces.items():
        if not ps:
            continue
        text = " ".join(p[2].strip() for p in _reading_order(ps) if p[2].strip())
        if text:
            out[vb] = (text, min(p[3] for p in ps))
    return out


def _reading_order(pieces: list[tuple]) -> list[tuple]:
    """Rows top to bottom, left to right in each. A row is every piece within ROW_TOLERANCE of the row's first
    (topmost) piece: rounding the centers instead splits a row whose words straddle a rounding boundary
    (`An Khánh Sơn, Nam Đàn, Nghệ`)."""
    rows: list[list[tuple]] = []
    for p in sorted(pieces, key=lambda p: p[0]):
        if rows and p[0] - rows[-1][0][0] <= ROW_TOLERANCE:
            rows[-1].append(p)
        else:
            rows.append([p])
    return [p for row in rows for p in sorted(row, key=lambda p: p[1])]


def extract_zone_fields(boxes: list[OcrBox], reg: Registration, template: dict, spec: ZoneSpec) -> dict[str, Field]:
    """Fields read by position, keyed like label mode. Fields absent from the template are not returned."""
    texts = zone_texts(boxes, reg, template, spec)
    # one row per labelled field; fields sharing its label (expiration date, issuing authority) join its row
    rows: dict[str, list[tuple]] = {}
    for key, f in template["fields"].items():
        head = f.get("shares_label", key)
        vb = tuple(f["value"]["box"])
        row = rows.setdefault(head, [])
        if vb not in row:
            row.append(vb)
    virtual: list[OcrBox] = []
    for i, (head, vbs) in enumerate(rows.items()):
        y = i * 100.0
        virtual.append(OcrBox(template["fields"][head]["label"][spec.label_lang], 1.0, (0, y, 50, y + 40), virtual=True))
        for j, vb in enumerate(vbs):
            if vb in texts:
                text, score = texts[vb]
                virtual.append(OcrBox(text, score, (100 + j * 1000, y, 1000 + j * 1000, y + 40)))
    fields = spec.parse(Document(virtual, spec.normalize))
    for f in fields.values():
        f.source = "zone"
    return {k: fields[k] for k in template["fields"] if k in fields}


def _same(a: str, b: str) -> bool:
    return re.sub(r"\s", "", a) == re.sub(r"\s", "", b)


def merge(label_fields: dict[str, Field], zone_fields: dict[str, Field]) -> dict[str, Field]:
    """hybrid: label result first; the position result fills gaps and confirms or questions it."""
    merged = {}
    for key, lf in label_fields.items():
        zf = zone_fields.get(key)
        if zf is None or zf.value is None:
            merged[key] = lf
        elif lf.value is None:
            zf.needs_review = True
            zf.notes.append("Không tìm được theo nhãn, lấy theo vị trí trên thẻ.")
            merged[key] = zf
        elif _same(lf.value, zf.value):
            lf.source = "label+zone"
            merged[key] = lf
        else:
            lf.needs_review = True
            lf.notes.append(f"Theo vị trí trên thẻ đọc ra: {zf.value}")
            merged[key] = lf
    return merged


def zones_px(reg: Registration, template: dict) -> dict[str, list[list[float]]]:
    """Each field's value box projected into the image, for drawing (4 corners, clockwise from top-left)."""
    h = card_h(template)
    out = {}
    for key, f in template["fields"].items():
        x0, y0, x1, y1 = f["value"]["box"]
        quad = reg.to_image(np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]) * [CARD_W, h])
        out[key] = [[round(float(x), 1), round(float(y), 1)] for x, y in quad]
    return out
