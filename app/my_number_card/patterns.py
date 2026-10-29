"""Printed text of the My Number card front, and the regexes reading it."""

from __future__ import annotations

import re

from ..card_core.pattern_card import MUNICIPAL_HEAD_RE, jp_normalize

TITLE_RE = re.compile(r"個\s*人\s*番\s*号\s*カ\s*[ー一-]?\s*ド|マ\s*イ\s*ナ\s*ン\s*バ\s*[ー一-]?\s*カ\s*[ー一-]?\s*ド|INDIVIDUAL\s*NUMBER", re.IGNORECASE)
# Printed labels, only used to judge OCR quality (the two fields have no label of their own).
LABELS = {
    "title": TITLE_RE,
    "name": re.compile(r"氏\s*名"),
    "address": re.compile(r"住\s*所"),
    "valid_marker": re.compile(r"ま\s*で\s*有\s*効"),
}
VALID_MARKER_RE = LABELS["valid_marker"]

# The expiry is "2035年 3月31日まで有効" (card_core.pattern_card.JP_DATE_RE, era years accepted too).
# The birth date line ends with 生 ("昭和60年 1月 1日生").
BIRTH_SUFFIX_RE = re.compile(r"\s*生")
ISSUER_RE = MUNICIPAL_HEAD_RE  # "○○市長", the last match wins


def normalize(text: str) -> str:
    return jp_normalize(text)
