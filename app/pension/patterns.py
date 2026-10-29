"""Printed text of the pension handbook / basic pension number notice, and the regexes reading it."""

from __future__ import annotations

import re

from ..card_core.pattern_card import jp_normalize

# 年金手帳 (issued until 2022-03) and 基礎年金番号通知書 (its replacement since 2022-04) carry the same number.
TITLE_RE = re.compile(r"年\s*金\s*手\s*帳|基\s*礎\s*年\s*金\s*番\s*号\s*通\s*知\s*書")
NUMBER_LABEL_RE = re.compile(r"基\s*礎\s*年\s*金\s*番\s*号(?!\s*通)")
# Printed labels, only used to judge OCR quality.
LABELS = {
    "title": TITLE_RE,
    "number": NUMBER_LABEL_RE,
    "name": re.compile(r"氏\s*名"),
    "birth": re.compile(r"生\s*年\s*月\s*日"),
}
# Basic pension number: 4 digits (office code) + 6 digits, printed "1234-567890".
NUMBER_RE = re.compile(r"(?<![0-9])([0-9OIlSBZDQ]{4})\s*[-－ー‐−—]\s*([0-9OIlSBZDQ]{6})(?![0-9])")
BARE_NUMBER_RE = re.compile(r"(?<![0-9])([0-9]{4})\s?([0-9]{6})(?![0-9])")
TO_DIGIT = str.maketrans({"O": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "S": "5", "B": "8", "Z": "2"})
ISSUE_LABEL_RE = re.compile(r"交\s*付\s*(?:年\s*月\s*日)?|発\s*行\s*(?:年\s*月\s*日)?")
NUMBER_WINDOW = 40  # characters after 基礎年金番号 where the number is printed (same line or below)


def normalize(text: str) -> str:
    return jp_normalize(text)
