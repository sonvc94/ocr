"""Health insurance card (健康保険証 / 資格確認書) front: card type (title), insurer name, date of issue.

Read by label/pattern on the flattened card text (card_core.layout), no template: mode=zone/hybrid fall back
to it with a warning.
"""

from __future__ import annotations

import datetime as dt
import re

from ..card_core.field import Field, finish
from ..card_core.layout import Document, drop_non_text
from ..card_core.pattern_card import JP_DATE_RE, build_result, jp_date
from ..ocr.types import OcrBox
from .patterns import INSURER_LABEL_RE, ISSUE_LABEL_RE, ISSUE_SUFFIX_RE, LABELS, NEXT_LABEL_RE, TITLE_RE, normalize

LABEL_GAP = 6  # the date follows its label on the same line (after ":" or a stray character)
VALUE_TRIM = " :：・.,|"


def _card_type(doc: Document) -> Field:
    f = Field()
    m = TITLE_RE.search(doc.text)
    if not m:
        return finish(f, None)
    f.raw = m.group(0)
    f.value = re.sub(r"\s+", "", m.group(0))
    if not m.group(1):
        f.notes.append("Không đọc được loại bảo hiểm (国民健康保険 / 健康保険 / …) trước tên thẻ.")
    return finish(f, doc.score(m.start(), m.end()))


def _insurer_name(doc: Document) -> Field:
    """Rest of the label's row, up to the next label; the next row when the value is printed below the label."""
    f = Field()
    for lab in INSURER_LABEL_RE.finditer(doc.text):
        start = lab.end()
        for _ in range(2):  # label's row, then the row below
            end = doc.text.find("\n", start)
            end = len(doc.text) if end < 0 else end
            nxt = NEXT_LABEL_RE.search(doc.text, start, end)
            stop = nxt.start() if nxt else end
            value = doc.text[start:stop].strip(VALUE_TRIM)
            value = re.sub(r"\s*印$", "", value)  # the insurer's seal mark
            if value:
                f.raw = doc.text[start:stop]
                f.value = value
                return finish(f, doc.score(start, stop))
            start = end + 1
            if start >= len(doc.text):
                break
    return finish(f, None)


def _issue_date(doc: Document) -> Field:
    """Date right after 交付年月日 (or 発行年月日), else a date directly followed by 交付."""
    f = Field()
    m = None
    for lab in ISSUE_LABEL_RE.finditer(doc.text):
        d = JP_DATE_RE.search(doc.text, lab.end(), lab.end() + LABEL_GAP + 20)
        if d and d.start() - lab.end() <= LABEL_GAP:
            m = d
            break
    if m is None:
        m = next((d for d in JP_DATE_RE.finditer(doc.text) if ISSUE_SUFFIX_RE.match(doc.text, d.end())), None)
    if m is None:
        return finish(f, None)
    f.raw = m.group(0)
    f.value = jp_date(m)
    if f.value is None:
        f.notes.append("Ngày không hợp lệ.")
    return finish(f, doc.score(m.start(), m.end()))


def cross_check(fields: dict[str, Field], today: dt.date | None = None) -> list[str]:
    warnings = []
    issued = fields["issue_date"]
    if issued.value and dt.date.fromisoformat(issued.value) > (today or dt.date.today()):
        issued.notes.append("Ngày cấp ở tương lai.")
        issued.needs_review = True
        warnings.append(f"Ngày cấp {issued.value} ở tương lai.")
    return warnings


def parse_health_insurance(
    boxes: list[OcrBox], page_size: tuple[int, int] | None = None, cropped: bool = False, mode: str = "label"
) -> dict:
    """Same signature as the other card parsers; `page_size`/`cropped` are unused (no template)."""
    boxes = drop_non_text(boxes)
    doc = Document(boxes, normalize)
    warnings: list[str] = []
    fields = {"card_type": _card_type(doc), "insurer_name": _insurer_name(doc), "issue_date": _issue_date(doc)}
    if fields["card_type"].value is None:
        warnings.append("Không tìm thấy tên thẻ (…被保険者証 / 資格確認書) — ảnh có thể không phải thẻ bảo hiểm y tế.")
    warnings += cross_check(fields)
    return build_result("health_insurance_card", fields, doc, LABELS, mode, warnings)
