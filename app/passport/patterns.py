"""Printed text of the Japanese passport photo page, and the regexes reading it."""

from __future__ import annotations

import re
import unicodedata

# Printed words, only used to judge OCR quality and to tell a Japanese passport.
LABELS = {
    "japan": re.compile(r"日\s*本\s*国|JAPAN"),
    "passport": re.compile(r"旅\s*券|PASSPORT", re.IGNORECASE),
    "number": re.compile(r"旅\s*券\s*番\s*号|Passport\s*No", re.IGNORECASE),
    "surname": re.compile(r"姓|Surname", re.IGNORECASE),
    "issuing_country": re.compile(r"発\s*行\s*国|Issuing\s*country", re.IGNORECASE),
}
JAPAN_RE = re.compile(r"日\s*本\s*国|JAPAN|P<JPN")
NUMBER_LABEL_RE = LABELS["number"]
# Japanese passport number: 2 letters + 7 digits (TR1234567).
NUMBER_RE = re.compile(r"(?<![A-Z0-9])([A-Z0-9]{2})\s?([0-9OIlSBZDQ]{7})(?![A-Z0-9])")
# MRZ line 2 (ICAO 9303 TD3): number (9) + check digit + nationality "JPN" + birth date…
MRZ2_RE = re.compile(r"([A-Z0-9<]{9})([0-9<])(JPN)[0-9<]{6}")
# OCR reads the filler "<" as these.
MRZ_FILLERS = str.maketrans({"«": "<<", "‹": "<", "く": "<", "〈": "<", "＜": "<", "≪": "<<"})
TO_DIGIT = str.maketrans({"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "l": "1", "S": "5", "B": "8", "Z": "2"})
TO_LETTER = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"})


def normalize(text: str) -> str:
    """NFKC turns full-width letters/digits into ASCII, which the regexes expect."""
    return unicodedata.normalize("NFKC", text).strip()


def mrz_check_digit(text: str) -> int:
    """ICAO 9303 check digit: weights 7, 3, 1; digits as is, A–Z = 10–35, "<" = 0."""
    total = 0
    for i, c in enumerate(text):
        v = int(c) if c.isdigit() else ord(c) - 55 if c.isalpha() else 0
        total += v * (7, 3, 1)[i % 3]
    return total % 10


def fix_number(letters: str, digits: str) -> str:
    """Japanese layout: positions 1–2 letters, 3–9 digits; undo OCR look-alikes by position."""
    return letters.translate(TO_LETTER) + digits.translate(TO_DIGIT)
