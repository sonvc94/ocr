"""Printed text of the certificate of residence (住民票の写し), and the regexes reading it."""

from __future__ import annotations

import re

from ..card_core.pattern_card import MUNICIPAL_HEAD_RE, jp_normalize

TITLE_RE = re.compile(r"住\s*民\s*票")
# Printed labels, only used to judge OCR quality.
LABELS = {
    "title": TITLE_RE,
    "name": re.compile(r"氏\s*名"),
    "address": re.compile(r"(?<!前)住\s*所"),
    "head": re.compile(r"世\s*帯\s*主"),
    "birth": re.compile(r"生\s*年\s*月\s*日"),
    "became_resident": re.compile(r"住\s*民\s*と\s*な\s*っ\s*た\s*(?:年\s*月\s*)?日"),
    "certify": re.compile(r"証\s*明\s*す\s*る"),
}
# "住所" but not "前住所" (previous address) nor "住所を定めた日" (date the address was set).
# OCR drops the small を ("住所定めた").
ADDRESS_LABEL_RE = re.compile(r"(?<!前)住\s*所(?!\s*を?\s*定)")
# A value that looks like an address: prefecture / municipality, or 丁目 / 番地 / 番 with digits.
ADDRESS_SHAPE_RE = re.compile(r"[都道府県].*[市区町村]|[市区町村].*\d|丁目|番地")
# Labels that end the address value when printed on the same row.
NEXT_LABEL_RE = re.compile(
    r"世\s*帯\s*主|氏\s*名|前\s*住\s*所|生\s*年\s*月\s*日|性\s*別|続\s*柄|本\s*籍|筆\s*頭\s*者|住\s*民\s*と\s*な\s*っ|"
    r"住\s*所\s*を?\s*定|届\s*出|住\s*民\s*票\s*コ|個\s*人\s*番\s*号|備\s*考|記\s*載\s*事\s*項|世\s*帯\s*全\s*員"
)
# "この写しは、住民票の原本と相違ないことを証明する。 令和5年4月1日 ○○市長 ○○ ○○ 印"
CERTIFY_RE = re.compile(r"証\s*明\s*(?:す\s*る|し\s*ま\s*す)")
ISSUER_RE = MUNICIPAL_HEAD_RE  # the last match is the certifying mayor
CERTIFY_WINDOW = 60  # characters after 証明する where its date is printed
ISSUER_WINDOW = 30  # 証明する not read: a date this close before the mayor's name is the certification date


def normalize(text: str) -> str:
    return jp_normalize(text)
