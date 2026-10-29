"""My Number card (個人番号カード) front: only the issuer ("○○市長") and the expiry date ("2035年 3月31日まで有効").

Neither field has a printed label, so both are read by pattern on the flattened card text (card_core.layout).
There is no template, so mode=zone/hybrid fall back to this with a warning.
"""

from __future__ import annotations

import datetime as dt

from ..card_core.field import Field, finish
from ..card_core.layout import Document, drop_non_text
from ..card_core.pattern_card import JP_DATE_RE, build_result, jp_date
from ..ocr.types import OcrBox
from .patterns import BIRTH_SUFFIX_RE, ISSUER_RE, LABELS, TITLE_RE, VALID_MARKER_RE, normalize

# The marker follows the date on the same line; allow a stray OCR character or a row break in between.
MARKER_GAP = 3
VALID_YEARS = 10  # issued for at most 10 years (until the 10th birthday after issuance)


def _expiry_date(doc: Document) -> Field:
    candidates = []  # (match, followed by まで有効)
    for m in JP_DATE_RE.finditer(doc.text):
        if BIRTH_SUFFIX_RE.match(doc.text, m.end()):
            continue
        marker = VALID_MARKER_RE.search(doc.text, m.end(), m.end() + MARKER_GAP + 8)
        candidates.append((m, marker is not None and marker.start() - m.end() <= MARKER_GAP))
    marked = [m for m, ok in candidates if ok]
    f = Field()
    if marked:
        m = marked[0]
    elif candidates:
        # "まで有効" not read: the expiry is the latest printed date (the birth date is the only other one).
        m = max((m for m, _ in candidates), key=lambda m: jp_date(m) or "")
        f.notes.append("Không đọc được chữ まで有効, đoán là ngày muộn nhất trên thẻ.")
    else:
        return finish(f, None)
    f.raw = m.group(0)
    f.value = jp_date(m)
    if f.value is None:
        f.notes.append("Ngày không hợp lệ.")
    return finish(f, doc.score(m.start(), m.end()))


def _issuer(doc: Document) -> Field:
    matches = list(ISSUER_RE.finditer(doc.text))
    f = Field()
    if not matches:
        return finish(f, None)
    m = matches[-1]
    f.raw = m.group(0)
    f.value = m.group(1) + "長"
    return finish(f, doc.score(m.start(), m.end()))


def cross_check(fields: dict[str, Field], today: dt.date | None = None) -> list[str]:
    warnings = []
    expiry = fields["expiry_date"]
    if expiry.value:
        today = today or dt.date.today()
        d = dt.date.fromisoformat(expiry.value)
        if d < today:
            warnings.append(f"Thẻ đã hết hạn ({expiry.value}).")
        elif d.year > today.year + VALID_YEARS:
            expiry.notes.append(f"Hạn thẻ quá {VALID_YEARS} năm kể từ hôm nay: có thể đọc sai năm.")
            expiry.needs_review = True
            warnings.append(f"Ngày hết hạn {expiry.value} vượt quá thời hạn tối đa {VALID_YEARS} năm của thẻ.")
    return warnings


def parse_my_number_card(
    boxes: list[OcrBox], page_size: tuple[int, int] | None = None, cropped: bool = False, mode: str = "label"
) -> dict:
    """Same signature as the other card parsers; `page_size`/`cropped` are unused (no template)."""
    boxes = drop_non_text(boxes)
    doc = Document(boxes, normalize)
    warnings: list[str] = []
    if not TITLE_RE.search(doc.text):
        warnings.append("Không tìm thấy chữ 個人番号カード — ảnh có thể không phải My Number Card.")
    fields = {"issuer": _issuer(doc), "expiry_date": _expiry_date(doc)}
    warnings += cross_check(fields)
    return build_result("my_number_card", fields, doc, LABELS, mode, warnings)
