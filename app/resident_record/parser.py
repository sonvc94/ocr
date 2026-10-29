"""Certificate of residence (住民票の写し): only the issuer ("○○市長"), the certification date and the address.

A full page, not a card: read without cropping (pipeline.DOCUMENTS), by label/pattern on the flattened text, no
template. My Number (個人番号) is masked before parsing (card_core.redact via pipeline) and never returned.
For a household extract the first 住所 is the household's address.
"""

from __future__ import annotations

import datetime as dt
import re

from ..card_core.field import Field, finish
from ..card_core.layout import Document, drop_non_text
from ..card_core.pattern_card import JP_DATE_RE, build_result, jp_date
from ..ocr.types import OcrBox
from .patterns import (
    ADDRESS_LABEL_RE,
    ADDRESS_SHAPE_RE,
    CERTIFY_RE,
    CERTIFY_WINDOW,
    ISSUER_RE,
    ISSUER_WINDOW,
    LABELS,
    NEXT_LABEL_RE,
    TITLE_RE,
    normalize,
)

VALUE_TRIM = " :：・.,|"


def _issuer(doc: Document) -> Field:
    matches = list(ISSUER_RE.finditer(doc.text))
    f = Field()
    if not matches:
        return finish(f, None)
    m = matches[-1]
    f.raw = m.group(0)
    f.value = m.group(1) + "長"
    return finish(f, doc.score(m.start(), m.end()))


def _certified_date(doc: Document, issuer: re.Match | None) -> Field:
    f = Field()
    dates = [m for m in JP_DATE_RE.finditer(doc.text) if jp_date(m)]
    m = None
    certify = list(CERTIFY_RE.finditer(doc.text))
    for c in certify:
        after = [d for d in dates if c.end() <= d.start() <= c.end() + CERTIFY_WINDOW]
        if after:
            m = after[0]
    if m is None and not certify and issuer is not None:
        before = [d for d in dates if 0 <= issuer.start() - d.end() <= ISSUER_WINDOW]
        if before:
            m = before[-1]
            f.notes.append("Không đọc được chữ 証明する, lấy ngày ngay trước tên nơi cấp.")
    if m is None:
        return finish(f, None)
    f.raw = m.group(0)
    f.value = jp_date(m)
    return finish(f, doc.score(m.start(), m.end()))


def _address(doc: Document) -> Field:
    """Rest of the label's row up to the next label; else the row below; else the row above (a table cell whose
    value is vertically centred lands on another row than its label) — those two only when it looks like an address."""
    f = Field()
    text = doc.text
    for lab in ADDRESS_LABEL_RE.finditer(text):
        row_start = text.rfind("\n", 0, lab.start()) + 1
        row_end = text.find("\n", lab.end())
        row_end = len(text) if row_end < 0 else row_end
        candidates = [(lab.end(), row_end, False)]
        if row_end < len(text):  # row below
            below_end = text.find("\n", row_end + 1)
            candidates.append((row_end + 1, len(text) if below_end < 0 else below_end, True))
        if row_start > 0:  # row above
            candidates.append((text.rfind("\n", 0, row_start - 1) + 1, row_start - 1, True))
        for start, end, check_shape in candidates:
            nxt = NEXT_LABEL_RE.search(text, start, end)
            stop = nxt.start() if nxt else end
            value = text[start:stop].strip(VALUE_TRIM)
            if value and (not check_shape or ADDRESS_SHAPE_RE.search(value)):
                f.raw = value
                f.value = re.sub(r"\s+", "", value)
                if check_shape:
                    f.notes.append("Địa chỉ không nằm cùng dòng với nhãn 住所, lấy ở dòng kề bên.")
                return finish(f, doc.score(start, stop))
    return finish(f, None)


def cross_check(fields: dict[str, Field], today: dt.date | None = None) -> list[str]:
    certified = fields["certified_date"]
    if certified.value and dt.date.fromisoformat(certified.value) > (today or dt.date.today()):
        certified.notes.append("Ngày chứng nhận ở tương lai.")
        certified.needs_review = True
        return [f"Ngày chứng nhận {certified.value} ở tương lai."]
    return []


def parse_resident_record(
    boxes: list[OcrBox], page_size: tuple[int, int] | None = None, cropped: bool = False, mode: str = "label"
) -> dict:
    """Same signature as the other parsers; `page_size`/`cropped` are unused (no template)."""
    boxes = drop_non_text(boxes)
    doc = Document(boxes, normalize)
    warnings: list[str] = []
    if not TITLE_RE.search(doc.text):
        warnings.append("Không tìm thấy chữ 住民票 — ảnh có thể không phải giấy chứng nhận cư trú.")
    issuers = list(ISSUER_RE.finditer(doc.text))
    fields = {
        "issuer": _issuer(doc),
        "certified_date": _certified_date(doc, issuers[-1] if issuers else None),
        "address": _address(doc),
    }
    warnings += cross_check(fields)
    return build_result("resident_record", fields, doc, LABELS, mode, warnings)
