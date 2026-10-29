"""Printed text of the driver's license front, and the regexes reading it."""

from __future__ import annotations

import re

from ..card_core.pattern_card import jp_normalize

TITLE_RE = re.compile(r"運\s*転\s*免\s*許\s*証")
# 運転経歴証明書 (issued after giving up the license): same card, same number (the former license number) and 交付 line.
HISTORY_TITLE_RE = re.compile(r"運\s*転\s*経\s*歴\s*証\s*明\s*書|運\s*転\s*経\s*歴")
# Printed words, only used to judge OCR quality.
LABELS = {
    "title": TITLE_RE,
    "name": re.compile(r"氏\s*名"),
    "address": re.compile(r"住\s*所"),
    "issue": re.compile(r"交\s*付"),
    "number": re.compile(r"番\s*号"),
    "commission": re.compile(r"公\s*安\s*委\s*員\s*会"),
}
# "番号 第 123456789012 号"; OCR spaces the digits out and mixes in look-alike letters.
NUMBER_RE = re.compile(r"第\s*([0-9OoDQIl|SBZ\s]{12,20}?)\s*号")
BARE_NUMBER_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")
TO_DIGIT = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "|": "1", "S": "5", "B": "8", "Z": "2"})
# "交付 令和03年05月10日 12345": the date is followed by a 5-digit reference number (照会番号), not part of it.
ISSUE_LABEL_RE = re.compile(r"交\s*付")
VALID_MARKER_RE = re.compile(r"ま\s*で?\s*有\s*効")  # small print: OCR drops で ("ま有効")
BIRTH_SUFFIX_RE = re.compile(r"\s*生")

# First 2 digits = the prefectural public safety commission that issued the license
# (Hokkaido has 5 area commissions: 10–14).
COMMISSION_CODES = {
    10: "札幌", 11: "函館", 12: "旭川", 13: "釧路", 14: "北見",
    20: "青森", 21: "岩手", 22: "宮城", 23: "秋田", 24: "山形", 25: "福島",
    30: "東京",
    40: "茨城", 41: "栃木", 42: "群馬", 43: "埼玉", 44: "千葉", 45: "神奈川", 46: "新潟", 47: "山梨", 48: "長野", 49: "静岡",
    50: "富山", 51: "石川", 52: "福井", 53: "岐阜", 54: "愛知", 55: "三重",
    60: "滋賀", 61: "京都", 62: "大阪", 63: "兵庫", 64: "奈良", 65: "和歌山",
    70: "鳥取", 71: "島根", 72: "岡山", 73: "広島", 74: "山口",
    80: "徳島", 81: "香川", 82: "愛媛", 83: "高知",
    90: "福岡", 91: "佐賀", 92: "長崎", 93: "熊本", 94: "大分", 95: "宮崎", 96: "鹿児島", 97: "沖縄",
}


def normalize(text: str) -> str:
    return jp_normalize(text)
