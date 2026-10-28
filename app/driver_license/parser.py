"""Driver's license (運転免許証) front: only the 12-digit license number and the date of issue (交付).

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
    BARE_NUMBER_RE,
    BIRTH_SUFFIX_RE,
    COMMISSION_CODES,
    ISSUE_LABEL_RE,
    LABELS,
    NUMBER_RE,
    TITLE_RE,
    TO_DIGIT,
    VALID_MARKER_RE,
    normalize,
)

LABEL_GAP = 4  # the date follows 交付 on the same line, after a stray OCR character at most


def _license_number(doc: Document) -> Field:
    f = Field()
    m = NUMBER_RE.search(doc.text)
    if m:
        raw = m.group(1)
        digits = "".join(raw.split()).translate(TO_DIGIT)
        if len(digits) != 12:
            m = None
    if not m:
        m = BARE_NUMBER_RE.search(doc.text)
        if not m:
            return finish(f, None)
        raw = digits = m.group(0)
        f.notes.append("Không thấy 第…号, lấy dãy 12 chữ số trên thẻ.")
    f.raw = m.group(0)
    f.value = digits
    if digits != "".join(raw.split()):
        f.notes.append("Đã sửa ký tự OCR đọc nhầm thành chữ số.")
    return finish(f, doc.score(m.start(), m.end()))


def _issue_date(doc: Document) -> Field:
    f = Field()
    dates = [m for m in JP_DATE_RE.finditer(doc.text) if jp_date(m)]
    labeled = [
        m for m in dates
        if any(0 <= m.start() - lab.end() <= LABEL_GAP for lab in ISSUE_LABEL_RE.finditer(doc.text, 0, m.start()))
    ]
    if labeled:
        m = labeled[0]
    else:
        # 交付 not read: the date that is neither the birth date (…生) nor the expiry (…まで有効).
        others = [
            m for m in dates
            if not BIRTH_SUFFIX_RE.match(doc.text, m.end()) and not VALID_MARKER_RE.search(doc.text, m.end(), m.end() + 4)
        ]
        if len(others) != 1:
            return finish(f, None)
        m = others[0]
        f.notes.append("Không đọc được chữ 交付, đoán theo vị trí giữa ngày sinh và ngày hết hạn.")
    f.raw = m.group(0)
    f.value = jp_date(m)
    return finish(f, doc.score(m.start(), m.end()))


def cross_check(fields: dict[str, Field], today: dt.date | None = None) -> list[str]:
    warnings = []
    number, issued = fields["license_number"], fields["issue_date"]
    if number.value and int(number.value[:2]) not in COMMISSION_CODES:
        number.notes.append("2 số đầu không phải mã công an tỉnh (公安委員会) nào.")
        number.needs_review = True
        warnings.append(f"Số bằng lái bắt đầu bằng {number.value[:2]}: không phải mã tỉnh hợp lệ, có thể đọc sai.")
    if issued.value and dt.date.fromisoformat(issued.value) > (today or dt.date.today()):
        issued.notes.append("Ngày cấp ở tương lai.")
        issued.needs_review = True
        warnings.append(f"Ngày cấp {issued.value} ở tương lai.")
    return warnings


def parse_driver_license(
    boxes: list[OcrBox], page_size: tuple[int, int] | None = None, cropped: bool = False, mode: str = "label"
) -> dict:
    """Same signature as the other card parsers; `page_size`/`cropped` are unused (no template)."""
    boxes = drop_non_text(boxes)
    doc = Document(boxes, normalize)
    warnings: list[str] = []
    # 運転免許証 is printed vertically next to the photo and often not read; 公安委員会 is printed on every license.
    if not TITLE_RE.search(doc.text) and not LABELS["commission"].search(doc.text):
        warnings.append("Không tìm thấy chữ 運転免許証 / 公安委員会 — ảnh có thể không phải bằng lái xe Nhật.")
    fields = {"license_number": _license_number(doc), "issue_date": _issue_date(doc)}
    warnings += cross_check(fields)
    return build_result("driver_license", fields, doc, LABELS, mode, warnings)
