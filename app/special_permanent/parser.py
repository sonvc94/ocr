"""Special Permanent Resident Certificate (特別永住者証明書) front: only the certificate number and the expiry date.

Read by pattern on the flattened card text (card_core.layout), no template: mode=zone/hybrid fall back to it
with a warning.
"""

from __future__ import annotations

import datetime as dt

from ..card_core.field import Field, finish
from ..card_core.layout import Document, drop_non_text
from ..card_core.pattern_card import JP_DATE_RE, build_result, jp_date
from ..ocr.types import OcrBox
from .patterns import (
    BIRTH_SUFFIX_RE,
    EXPIRY_LABEL_RE,
    LABELS,
    NUMBER_RE,
    TITLE_RE,
    TO_DIGIT,
    TO_LETTER,
    VALID_MARKER_RE,
    normalize,
)

LABEL_GAP = 6  # the date follows the expiry label on the same line or the next one
MARKER_GAP = 3


def _number(doc: Document) -> Field:
    f = Field()
    m = NUMBER_RE.search(doc.text)
    if not m:
        return finish(f, None)
    head, digits, tail = m.group(1), m.group(2), m.group(3)
    value = head.translate(TO_LETTER) + digits.translate(TO_DIGIT) + tail.translate(TO_LETTER)
    f.raw = m.group(0)
    f.value = value
    if value != head + digits + tail:
        f.notes.append("Đã sửa ký tự OCR đọc nhầm (chữ ↔ số) theo dạng 2 chữ + 8 số + 2 chữ.")
    return finish(f, doc.score(m.start(), m.end()))


def _expiry_date(doc: Document) -> Field:
    f = Field()
    dates = [m for m in JP_DATE_RE.finditer(doc.text) if jp_date(m) and not BIRTH_SUFFIX_RE.match(doc.text, m.end())]
    labeled = [
        m for m in dates
        if any(0 <= m.start() - lab.end() <= LABEL_GAP for lab in EXPIRY_LABEL_RE.finditer(doc.text, 0, m.start()))
    ]
    marked = [m for m in dates if (v := VALID_MARKER_RE.search(doc.text, m.end(), m.end() + MARKER_GAP + 6))
              and v.start() - m.end() <= MARKER_GAP]
    if labeled or marked:
        m = (labeled or marked)[0]
    elif dates:
        m = max(dates, key=jp_date)
        f.notes.append("Không đọc được nhãn hạn (有効期間の満了日 / まで有効), đoán là ngày muộn nhất.")
    else:
        return finish(f, None)
    f.raw = m.group(0)
    f.value = jp_date(m)
    return finish(f, doc.score(m.start(), m.end()))


def cross_check(fields: dict[str, Field], today: dt.date | None = None) -> list[str]:
    expiry = fields["expiry_date"]
    if expiry.value and dt.date.fromisoformat(expiry.value) < (today or dt.date.today()):
        return [f"Giấy chứng nhận đã hết hạn ({expiry.value})."]
    return []


def parse_special_permanent(
    boxes: list[OcrBox], page_size: tuple[int, int] | None = None, cropped: bool = False, mode: str = "label"
) -> dict:
    """Same signature as the other card parsers; `page_size`/`cropped` are unused (no template)."""
    boxes = drop_non_text(boxes)
    doc = Document(boxes, normalize)
    warnings: list[str] = []
    if not TITLE_RE.search(doc.text):
        warnings.append("Không tìm thấy chữ 特別永住者証明書 — ảnh có thể không phải giấy chứng nhận vĩnh trú đặc biệt.")
    fields = {"certificate_number": _number(doc), "expiry_date": _expiry_date(doc)}
    warnings += cross_check(fields)
    return build_result("special_permanent_resident_certificate", fields, doc, LABELS, mode, warnings)
