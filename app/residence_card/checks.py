"""Card-level judgements: which card design it is, whether OCR quality is trustworthy, date consistency."""

from __future__ import annotations

import re
from datetime import date

from ..card_core import quality
from ..card_core.field import Field
from ..card_core.layout import Document
from .patterns import FIELD_LABELS


def card_design(text: str, labels: dict) -> str:
    if re.search(r"個\s*人\s*番?\s*号?|特\s*定\s*在\s*留", text):
        return "specified_2026"  # 特定在留カード (residence card + My Number card), different layout
    no_permission_rows = "permission_type" not in labels and "issue_date" not in labels
    if re.search(r"\bISA\b", text) or (no_permission_rows and re.search(r"在\s*留\s*期\s*間\s*満", text)):
        return "2026"
    return "2012"


def assess_quality(doc: Document, jp_labels_found: int) -> dict:
    return quality.assess_quality(doc, jp_labels_found, len(FIELD_LABELS), "tiếng Nhật")


def cross_check(fields: dict[str, Field]) -> list[str]:
    def d(key: str) -> date | None:
        v = fields[key].value
        return date.fromisoformat(v) if v else None

    warnings = []
    dob, issued, permitted = d("date_of_birth"), d("issue_date"), d("permission_date")
    expires, valid = d("expiration_date"), d("valid_until")
    if dob and issued and dob >= issued:
        warnings.append("Ngày sinh không trước ngày cấp thẻ.")
        fields["date_of_birth"].needs_review = True
    if permitted and issued and permitted > issued:
        warnings.append("Ngày cấp phép sau ngày cấp thẻ.")
    if issued and expires and expires < issued:
        warnings.append("Ngày hết hạn lưu trú trước ngày cấp thẻ.")
        fields["expiration_date"].needs_review = True
    if expires and valid and expires != valid:
        warnings.append("Ngày hết hạn lưu trú khác ngày hết hiệu lực thẻ (bình thường chỉ khác với 永住者).")
    if valid and valid < date.today():
        warnings.append("Thẻ đã hết hiệu lực.")
    return warnings
