"""Pension handbook (国民年金手帳) / basic pension number notice (基礎年金番号通知書): the basic pension number and
the date of issue.

A booklet page or a paper notice, not an ID-1 card: read without cropping (pipeline.DOCUMENTS), by label/pattern
on the flattened text, no template.
"""

from __future__ import annotations

import datetime as dt

from ..card_core.field import Field, finish
from ..card_core.layout import Document, drop_non_text
from ..card_core.pattern_card import JP_DATE_RE, build_result, jp_date
from ..ocr.types import OcrBox
from .patterns import (
    BARE_NUMBER_RE,
    ISSUE_LABEL_RE,
    LABELS,
    NUMBER_LABEL_RE,
    NUMBER_RE,
    NUMBER_WINDOW,
    TITLE_RE,
    TO_DIGIT,
    normalize,
)

LABEL_GAP = 6


def _pension_number(doc: Document) -> Field:
    f = Field()
    labels = list(NUMBER_LABEL_RE.finditer(doc.text))
    near = [m for m in NUMBER_RE.finditer(doc.text) if any(0 <= m.start() - lab.end() <= NUMBER_WINDOW for lab in labels)]
    m = near[0] if near else NUMBER_RE.search(doc.text)
    if m is None:
        m = BARE_NUMBER_RE.search(doc.text)
        if m is None:
            return finish(f, None)
        f.notes.append("Không thấy dạng 1234-567890, lấy dãy 10 chữ số trên giấy.")
    elif not near:
        f.notes.append("Không đọc được nhãn 基礎年金番号 ngay trước số.")
    head, tail = m.group(1), m.group(2)
    digits = (head + tail).translate(TO_DIGIT)
    f.raw = m.group(0)
    f.value = f"{digits[:4]}-{digits[4:]}"
    if digits != head + tail:
        f.notes.append("Đã sửa ký tự OCR đọc nhầm thành chữ số.")
    return finish(f, doc.score(m.start(), m.end()))


def _issue_date(doc: Document) -> Field:
    f = Field()
    dates = [m for m in JP_DATE_RE.finditer(doc.text) if jp_date(m)]
    labeled = [
        m for m in dates
        if any(0 <= m.start() - lab.end() <= LABEL_GAP for lab in ISSUE_LABEL_RE.finditer(doc.text, 0, m.start()))
    ]
    if not labeled:
        return finish(f, None)  # the other dates (birth, enrolment) cannot be told apart from it
    m = labeled[0]
    f.raw = m.group(0)
    f.value = jp_date(m)
    return finish(f, doc.score(m.start(), m.end()))


def cross_check(fields: dict[str, Field], today: dt.date | None = None) -> list[str]:
    issued = fields["issue_date"]
    if issued.value and dt.date.fromisoformat(issued.value) > (today or dt.date.today()):
        issued.notes.append("Ngày cấp ở tương lai.")
        issued.needs_review = True
        return [f"Ngày cấp {issued.value} ở tương lai."]
    return []


def parse_pension(
    boxes: list[OcrBox], page_size: tuple[int, int] | None = None, cropped: bool = False, mode: str = "label"
) -> dict:
    """Same signature as the other parsers; `page_size`/`cropped` are unused (no template)."""
    boxes = drop_non_text(boxes)
    doc = Document(boxes, normalize)
    warnings: list[str] = []
    if not TITLE_RE.search(doc.text) and not NUMBER_LABEL_RE.search(doc.text):
        warnings.append("Không tìm thấy chữ 年金手帳 / 基礎年金番号 — ảnh có thể không phải sổ / thông báo số hưu trí.")
    fields = {"basic_pension_number": _pension_number(doc), "issue_date": _issue_date(doc)}
    warnings += cross_check(fields)
    return build_result("pension_book", fields, doc, LABELS, mode, warnings)
