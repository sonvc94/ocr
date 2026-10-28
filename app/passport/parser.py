"""Japanese passport photo page: only the passport number.

Two sources: the printed number under 旅券番号 / Passport No., and the machine-readable zone (MRZ line 2,
characters 1–9 + check digit). The MRZ check digit is what makes a number trustworthy without a human look.
The photo page is not an ID-1 card (and a passport is usually photographed open), so the pipeline does not
crop it (pipeline.DOCUMENTS); there is no template either: mode=zone/hybrid fall back with a warning.
"""

from __future__ import annotations

import re

from ..card_core.field import Field, finish
from ..card_core.layout import Document, drop_non_text
from ..card_core.pattern_card import build_result
from ..ocr.types import OcrBox
from .patterns import (
    JAPAN_RE,
    LABELS,
    MRZ2_RE,
    MRZ_FILLERS,
    NUMBER_LABEL_RE,
    NUMBER_RE,
    fix_number,
    mrz_check_digit,
    normalize,
)

LABEL_WINDOW = 40  # the number is printed under its label: look this many characters past it (next row)
NUMBER_SHAPE = re.compile(r"[A-Z]{2}\d{7}")


def _mrz_number(doc: Document) -> tuple[str, bool, float | None] | None:
    """(number, check digit ok, OCR score) from MRZ line 2, or None."""
    for row in doc.text.split("\n"):
        line = "".join(row.split()).translate(MRZ_FILLERS).upper()
        m = MRZ2_RE.search(line)
        if not m:
            continue
        raw = m.group(1).rstrip("<")
        number = fix_number(raw[:2], raw[2:]) if len(raw) == 9 else raw
        ok = m.group(2).isdigit() and mrz_check_digit(number) == int(m.group(2))
        start = doc.text.find(row)
        return number, ok, doc.score(start, start + len(row))
    return None


def _printed_number(doc: Document) -> tuple[str, str, float | None, bool] | None:
    """(number, raw, OCR score, found next to its label) of the printed number, or None."""
    mrz_rows = {i for i, row in enumerate(doc.text.split("\n")) if "<<" in row.translate(MRZ_FILLERS)}
    candidates = []
    pos = 0
    for i, row in enumerate(doc.text.split("\n")):
        if i not in mrz_rows:
            candidates += [(pos + m.start(), pos + m.end(), m) for m in NUMBER_RE.finditer(row)]
        pos += len(row) + 1
    labels = [lab.end() for lab in NUMBER_LABEL_RE.finditer(doc.text)]
    for start, end, m in candidates:
        number = fix_number(m.group(1), m.group(2))
        if NUMBER_SHAPE.fullmatch(number) and any(0 <= start - e <= LABEL_WINDOW for e in labels):
            return number, m.group(0), doc.score(start, end), True
    for start, end, m in candidates:
        number = fix_number(m.group(1), m.group(2))
        if NUMBER_SHAPE.fullmatch(number) and m.group(1).isalpha():  # no label: stricter, real letters only
            return number, m.group(0), doc.score(start, end), False
    return None


def _passport_number(doc: Document) -> Field:
    f = Field()
    mrz, printed = _mrz_number(doc), _printed_number(doc)
    if mrz and mrz[1]:
        f.value, f.raw = mrz[0], mrz[0]
        score = mrz[2]
        if printed and printed[0] != mrz[0]:
            f.notes.append(f"Số in trên trang ({printed[0]}) khác số trong MRZ; lấy theo MRZ (đúng check digit).")
        return finish(f, score)
    if printed:
        f.value, f.raw, score = printed[0], printed[1], printed[2]
        if not printed[3]:
            f.notes.append("Không thấy nhãn 旅券番号 / Passport No., lấy dãy có dạng số hộ chiếu.")
        if mrz:
            if mrz[0] != printed[0]:
                f.notes.append(f"MRZ đọc ra {mrz[0]}, sai check digit.")
        return finish(f, score)
    if mrz:
        f.value, f.raw = mrz[0], mrz[0]
        f.notes.append("Chỉ đọc được MRZ và sai check digit.")
        return finish(f, mrz[2])
    return finish(f, None)


def parse_passport(
    boxes: list[OcrBox], page_size: tuple[int, int] | None = None, cropped: bool = False, mode: str = "label"
) -> dict:
    """Same signature as the other card parsers; `page_size`/`cropped` are unused (no template)."""
    boxes = drop_non_text(boxes)
    doc = Document(boxes, normalize)
    warnings: list[str] = []
    if not JAPAN_RE.search(doc.text):
        warnings.append("Không tìm thấy chữ 日本国 / JAPAN — có thể không phải hộ chiếu Nhật (chỉ hỗ trợ hộ chiếu Nhật).")
    fields = {"passport_number": _passport_number(doc)}
    number = fields["passport_number"]
    if number.value and not NUMBER_SHAPE.fullmatch(number.value):
        number.notes.append("Không đúng dạng số hộ chiếu Nhật (2 chữ + 7 số).")
        number.needs_review = True
    return build_result("passport", fields, doc, LABELS, mode, warnings)
