"""Printed text of the My Number card front, and the regexes reading it."""

from __future__ import annotations

import re
import unicodedata

TITLE_RE = re.compile(r"個\s*人\s*番\s*号\s*カ\s*[ー一-]?\s*ド|マ\s*イ\s*ナ\s*ン\s*バ\s*[ー一-]?\s*カ\s*[ー一-]?\s*ド|INDIVIDUAL\s*NUMBER", re.IGNORECASE)
# Printed labels, only used to judge OCR quality (the two fields have no label of their own).
LABELS = {
    "title": TITLE_RE,
    "name": re.compile(r"氏\s*名"),
    "address": re.compile(r"住\s*所"),
    "valid_marker": re.compile(r"ま\s*で\s*有\s*効"),
}
VALID_MARKER_RE = LABELS["valid_marker"]

# "2035年 3月31日まで有効" (Western year); era years accepted too in case a card prints one.
ERAS = {"令和": 2018, "平成": 1988, "昭和": 1925}
DATE_RE = re.compile(r"(令\s*和|平\s*成|昭\s*和)?\s*(\d{1,4}|元)\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
# The birth date line ends with 生 ("昭和60年 1月 1日生").
BIRTH_SUFFIX_RE = re.compile(r"\s*生")
# Issuer: head of the municipality, printed as "○○市長" / "○○区長" / "○○町長" / "○○村長". The lookahead keeps
# an address such as "千代田区長田町" out; the last match wins (the issuer is printed below the address).
ISSUER_RE = re.compile(r"([぀-ヿ一-鿿々]{1,24}?[市区町村])\s*長(?![一-鿿])")  # kana too: さいたま市, 鎌ケ谷市


def normalize(text: str) -> str:
    """NFKC turns full-width digits into ASCII, which the regexes expect."""
    return unicodedata.normalize("NFKC", text).strip()
