"""Printed text of the health insurance card front, and the regexes reading it.

Cards stopped being issued on 2024-12-02 (replaced by マイナ保険証); people without one get a 資格確認書,
laid out like the old card, so both titles are accepted.
"""

from __future__ import annotations

import re
import unicodedata

# Card type = the title: scheme + kind of card ("国民健康保険被保険者証", "健康保険資格確認書", "組合員証"…).
SCHEMES = r"国民健康保険|健康保険|後期高齢者医療|船員保険|(?:国家公務員|地方職員|公立学校|警察|私立学校教職員)?共済組合"
KINDS = r"被保険者証|被扶養者証|資格確認書|組合員証|加入者証"
TITLE_RE = re.compile(rf"((?:{SCHEMES})\s*)?({KINDS})")

# Insurer: 保険者名称 (employee/health-society cards), 交付者名 / 保険者 (municipal National Health Insurance).
INSURER_LABEL_RE = re.compile(r"保\s*険\s*者\s*名\s*称|交\s*付\s*者\s*名|(?<!被)保\s*険\s*者(?!\s*(?:番|所|証|名|氏))")
# Labels that can follow the insurer on the same row.
NEXT_LABEL_RE = re.compile(r"保\s*険\s*者\s*(?:番\s*号|所\s*在\s*地)|事\s*業\s*所|所\s*在\s*地|電\s*話|印\s*$")
ISSUE_LABEL_RE = re.compile(r"交\s*付\s*年\s*月\s*日|発\s*行\s*年\s*月\s*日|交\s*付\s*日")
# Some cards print the date first: "令和 5年 4月 1日交付" (協会けんぽ).
ISSUE_SUFFIX_RE = re.compile(r"\s*(?:交\s*付|発\s*行)(?!\s*(?:者|年))")

# Printed words, only used to judge OCR quality.
LABELS = {
    "title": TITLE_RE,
    "insurer": INSURER_LABEL_RE,
    "issue": ISSUE_LABEL_RE,
    "name": re.compile(r"氏\s*名"),
    "insurer_number": re.compile(r"保\s*険\s*者\s*番\s*号"),
}


def normalize(text: str) -> str:
    """NFKC turns full-width digits/brackets into ASCII, which the regexes expect."""
    return unicodedata.normalize("NFKC", text).strip()
