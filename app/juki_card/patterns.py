"""Printed text of the Basic Resident Register Card (住基カード) front, and the regexes reading it."""

from __future__ import annotations

import re

from ..card_core.pattern_card import MUNICIPAL_HEAD_RE, jp_normalize

TITLE_RE = re.compile(r"住\s*民\s*基\s*本\s*台\s*帳\s*カ\s*[ー一-]?\s*ド|住\s*基\s*カ\s*[ー一-]?\s*ド")
# Printed labels, only used to judge OCR quality.
LABELS = {
    "title": TITLE_RE,
    "name": re.compile(r"氏\s*名"),
    "address": re.compile(r"住\s*所"),
    "expiry": re.compile(r"有\s*効\s*期\s*限|ま\s*で\s*有\s*効"),
}
# Expiry: "有効期限 平成37年3月31日" or "…まで有効".
EXPIRY_LABEL_RE = re.compile(r"有\s*効\s*期\s*限")
VALID_MARKER_RE = re.compile(r"ま\s*で\s*有\s*効")
BIRTH_SUFFIX_RE = re.compile(r"\s*生")
ISSUER_RE = MUNICIPAL_HEAD_RE  # "○○市長", the last match wins
# The card prints the issuing municipality alone on its own line ("横浜市"); the specimens use placeholders (△△市).
MUNICIPALITY_LINE_RE = re.compile(r"^\s*([぀-ヿ一-鿿々△○□]{1,24}?[市区町村])(?:\s|$)")

# Issued from 2003-08 to 2015-12, valid for 10 years: none is valid after 2025-12.
LAST_ISSUE = "2015-12-31"


def normalize(text: str) -> str:
    return jp_normalize(text)
