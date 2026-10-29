"""Printed text of the Special Permanent Resident Certificate front, and the regexes reading it."""

from __future__ import annotations

import re

from ..card_core.pattern_card import jp_normalize

TITLE_RE = re.compile(r"特\s*別\s*永\s*住\s*者\s*証\s*明\s*書|SPECIAL\s*PERMANENT\s*RESIDENT", re.IGNORECASE)
# Printed labels, only used to judge OCR quality.
LABELS = {
    "title": TITLE_RE,
    "name": re.compile(r"氏\s*名"),
    "birth": re.compile(r"生\s*年\s*月\s*日"),
    "nationality": re.compile(r"国\s*籍\s*[・·]?\s*地\s*域"),
    "address": re.compile(r"住\s*居\s*地"),
    "expiry": re.compile(r"有\s*効\s*期\s*間|ま\s*で\s*有\s*効"),
}
# Same format as the residence card number: 2 letters, 8 digits, 2 letters ("AB12345678CD").
NUMBER_RE = re.compile(r"(?<![A-Z0-9])([A-Z0-9]{2})\s?([0-9OIlSBZDQ]{8})\s?([A-Z0-9]{2})(?![A-Z0-9])")
TO_DIGIT = str.maketrans({"O": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "S": "5", "B": "8", "Z": "2"})
TO_LETTER = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"})
# Expiry: "有効期間の満了日 2030年12月31日" or "…日まで有効" (cards of holders under 16: "16歳の誕生日").
EXPIRY_LABEL_RE = re.compile(r"有\s*効\s*期\s*間\s*(?:の\s*)?満\s*了\s*日|有\s*効\s*期\s*限")
VALID_MARKER_RE = re.compile(r"ま\s*で\s*有\s*効")
BIRTH_SUFFIX_RE = re.compile(r"\s*生")


def normalize(text: str) -> str:
    return jp_normalize(text)
