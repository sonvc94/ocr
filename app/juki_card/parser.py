"""Basic Resident Register Card (住民基本台帳カード) front: only the issuer (the municipality, "横浜市" / "○○市長") and the expiry date.

Read by pattern on the flattened card text (card_core.layout), no template: mode=zone/hybrid fall back to it
with a warning. The card was issued until 2015-12 for 10 years, so every card has now expired (always warned).
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
    ISSUER_RE,
    LABELS,
    LAST_ISSUE,
    MUNICIPALITY_LINE_RE,
    TITLE_RE,
    VALID_MARKER_RE,
    normalize,
)

LABEL_GAP = 6
MARKER_GAP = 3
VALID_YEARS = 10


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
        f.notes.append("Không đọc được nhãn 有効期限 / まで有効, đoán là ngày muộn nhất trên thẻ.")
    else:
        return finish(f, None)
    f.raw = m.group(0)
    f.value = jp_date(m)
    return finish(f, doc.score(m.start(), m.end()))


def _issuer(doc: Document) -> Field:
    """"○○市長" if printed; otherwise the line starting with the municipality name alone ("横浜市"), as the card prints it."""
    f = Field()
    matches = list(ISSUER_RE.finditer(doc.text))
    if matches:
        m = matches[-1]
        f.raw = m.group(0)
        f.value = m.group(1) + "長"
        return finish(f, doc.score(m.start(), m.end()))
    pos = 0
    for row in doc.text.split("\n"):
        m = MUNICIPALITY_LINE_RE.match(row)
        if m:
            f.raw = m.group(1)
            f.value = m.group(1)
            return finish(f, doc.score(pos + m.start(1), pos + m.end(1)))
        pos += len(row) + 1
    return finish(f, None)


def cross_check(fields: dict[str, Field], today: dt.date | None = None) -> list[str]:
    warnings = []
    expiry = fields["expiry_date"]
    if expiry.value:
        d = dt.date.fromisoformat(expiry.value)
        if d < (today or dt.date.today()):
            warnings.append(f"Thẻ đã hết hạn ({expiry.value}).")
        last = dt.date.fromisoformat(LAST_ISSUE)
        if d > last.replace(year=last.year + VALID_YEARS):
            expiry.notes.append(f"Thẻ ngừng cấp từ 12/2015, hạn tối đa {VALID_YEARS} năm: hạn này không thể có, có thể đọc sai năm.")
            expiry.needs_review = True
    else:
        warnings.append("住基カード ngừng cấp từ 12/2015 (hạn tối đa 10 năm): mọi thẻ đã hết hạn từ 12/2025.")
    return warnings


def parse_juki_card(
    boxes: list[OcrBox], page_size: tuple[int, int] | None = None, cropped: bool = False, mode: str = "label"
) -> dict:
    """Same signature as the other card parsers; `page_size`/`cropped` are unused (no template)."""
    boxes = drop_non_text(boxes)
    doc = Document(boxes, normalize)
    warnings: list[str] = []
    if not TITLE_RE.search(doc.text):
        warnings.append("Không tìm thấy chữ 住民基本台帳カード — ảnh có thể không phải Basic Resident Register Card.")
    fields = {"issuer": _issuer(doc), "expiry_date": _expiry_date(doc)}
    warnings += cross_check(fields)
    return build_result("juki_card", fields, doc, LABELS, mode, warnings)
