"""Shared pieces of the documents read by text pattern only (no template): Japanese dates, the result dict.

Used by my_number_card, driver_license, passport, health_insurance. Japanese dates are a writing convention,
not the printed layout of a particular card, so they belong here.
"""

from __future__ import annotations

import datetime as dt
import re

from .field import Field
from .layout import Document
from .quality import assess_quality

ERAS = {"令和": 2018, "R": 2018, "平成": 1988, "H": 1988, "昭和": 1925, "S": 1925}
# "2035年 3月31日", "令和 3年 5月10日", "令和元年…", "R5. 4. 1" / "令和5.4.1" (health insurance cards).
JP_DATE_RE = re.compile(
    r"(令\s*和|平\s*成|昭\s*和|(?<![A-Za-z])[RHS](?=\s*\d{1,2}\s*\.))?\s*(\d{1,4}|元)\s*(?:年|\.)\s*(\d{1,2})\s*(?:月|\.)\s*(\d{1,2})\s*日?"
)
NO_TEMPLATE_WARNING = "Loại giấy tờ này chưa có template vị trí: chỉ dùng kết quả theo mẫu chữ."


def jp_date(m: re.Match) -> str | None:
    """ISO date from a JP_DATE_RE match; None when it is not a real date (or an era year without its era)."""
    era, year, month, day = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
    y = 1 if year == "元" else int(year)
    if era:
        y += ERAS[era.replace(" ", "")]
    elif y < 1900:  # "05年" without its era cannot be placed
        return None
    try:
        return dt.date(y, month, day).isoformat()
    except ValueError:
        return None


def build_result(
    document_type: str,
    fields: dict[str, Field],
    doc: Document,
    labels: dict[str, re.Pattern],
    mode: str,
    warnings: list[str],
    card_design: str | None = None,
) -> dict:
    """Same shape as the template-based parsers' results. `labels` = printed words counted for quality."""
    found = sorted(k for k, p in labels.items() if p.search(doc.text))
    quality = assess_quality(doc, len(found), len(labels), "tiếng Nhật")
    if quality["level"] == "low":
        for f in fields.values():
            if f.value is not None:
                f.needs_review = True
    if mode != "label":
        warnings = [*warnings, NO_TEMPLATE_WARNING]
    return {
        "document_type": document_type,
        "side": "front",
        "card_design": card_design,
        "fields": {k: v.to_dict() for k, v in fields.items()},
        "quality": quality,
        "warnings": warnings,
        "mean_ocr_confidence": None if doc.mean_score is None else round(doc.mean_score, 4),
        "labels_found": found,
        "labels_from_english_anchor": [],
        "layout": {"mode": mode, "registration": None, "zones_px": {}},
        "full_text": doc.text,
    }
