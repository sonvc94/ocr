"""What is printed on the card: label patterns, value formats, official wordings, OCR confusions."""

from __future__ import annotations

import re
import unicodedata

# Label patterns, in the order they appear on the card. Negative lookaheads keep a label
# from matching inside a value (e.g. "在留期間更新許可" is a permission type, not a label).
LABELS: dict[str, str] = {
    "card_number": r"番号",
    "name": r"氏\s*名",
    "date_of_birth": r"生\s*年\s*月\s*日",
    "sex": r"性\s*別",
    "nationality": r"国\s*籍\s*[・･·]?\s*(?:地\s*[域城])?|国\s*[・･·]\s*地\s*[域城]",
    "address": r"住\s*居\s*地",
    "status_of_residence": r"在\s*留\s*資\s*格(?!に基づく|変更|取得)",
    "work_restriction": r"就\s*労\s*制\s*限\s*(?:の\s*)?有\s*無",
    "period_of_stay": r"在\s*留\s*期\s*間(?!更新)\s*(?:[(（]\s*満\s*了\s*日\s*[)）])?",
    "permission_type": r"許\s*可\s*(?:の\s*)?種\s*類",
    "permission_date": r"許\s*可\s*年\s*月\s*日",
    "issue_date": r"交\s*付\s*年\s*月\s*日",
    "valid_until_marker": r"この\s*カ\s*[ー一-]?\s*ド\s*は",
}
# card_number and the validity sentence are not field labels
FIELD_LABELS = LABELS.keys() - {"card_number", "valid_until_marker"}

# English sub-labels are printed right under the Japanese label and OCR reads them far more
# reliably than kanji. When a Japanese label is unreadable, its position is recovered from these.
ENGLISH_ANCHORS: dict[str, tuple[str, str]] = {
    "name": (r"^NAME$", "氏名"),
    "date_of_birth": (r"^DATE\s*OF\s*BIRTH", "生年月日"),
    "sex": (r"^SEX\b", "性別"),
    "nationality": (r"^NATIONALITY", "国籍・地域"),
    "address": (r"^ADDRESS$", "住居地"),
    "status_of_residence": (r"^STATUS\b", "在留資格"),
    "period_of_stay": (r"^\(?PERIOD\s*OF\s*STAY", "在留期間"),
    "permission_type": (r"^TYPE\s*OF\s*PERMISSION", "許可の種類"),
    "permission_date": (r"^DATE\s*OF\s*PERMISSION", "許可年月日"),
    "issue_date": (r"^DATE\s*OF\s*ISSUE", "交付年月日"),
}
RESIDENCE_CARD_TITLE = re.compile(r"在\s*留\s*カ\s*[ー一-]?\s*ド|RESIDENCE\s*CARD", re.IGNORECASE)
PERMISSION_TYPE_RE = re.compile(r"(?:在留期間更新|在留資格変更|在留資格取得|永住|上陸)許可")
CJK_RE = re.compile(r"[぀-ヿ一-鿿]")

# Since 2026-06-14 the card no longer prints these; they are only stored in the IC chip.
NOT_PRINTED_SINCE_2026 = ("period_of_stay", "permission_type", "issuing_authority", "permission_date", "issue_date")

# English sub-labels printed under the Japanese ones; stripped from values.
# OCR often drops the spaces inside them, so spaces are optional.
ENGLISH_SUBLABELS = re.compile(
    r"\b(?:NAME|DATE\s*OF\s*BIRTH|SEX|NATIONALITY\s*/?\s*REGION|ADDRESS|STATUS|"
    r"PERIOD\s*OF\s*STAY|DATE\s*OF\s*EXPIRATION|TYPE\s*OF\s*PERMISSION|DATE\s*OF\s*PERMISSION|"
    r"DATE\s*OF\s*ISSUE|RESIDENCE\s*CARD|GOVERNMENT\s*OF\s*JAPAN|PERIOD\s*OF\s*VALIDITY\s*OF\s*THIS\s*CARD|"
    r"WORK\s*RESTRICTIONS|THE\s*EXPIRY\s*DATE\s*OF\s*THE\s*PERIOD\s*OF\s*STAY|ISA|MOJ|SAMPLE)\b",
    re.IGNORECASE,
)
# Other print that is not part of any value: Y M D unit markers under dates, the 見本 stamp on specimen cards.
NOISE = re.compile(r"(?:\b[YMD]\b\.?\s*){2,}|見本[・·]?|[()]\s*[()]|[<>]")

# PP-OCRv5 is trained on Chinese + Japanese together and sometimes emits the simplified
# Chinese form or a look-alike kanji/katakana. Only characters that never appear on the card
# in the "wrong" form are mapped globally.
CONFUSABLES = str.maketrans({
    "资": "資", "别": "別", "职": "職", "间": "間", "许": "許", "类": "類", "满": "満", "劳": "労",
    "务": "務", "识": "識", "际": "際", "业": "業", "术": "術", "经": "経", "营": "営", "卜": "ト", "滿": "満",
})
# Katakana read in place of kanji numerals inside addresses (二丁目, 八番...).
ADDRESS_NUMERAL_FIX = re.compile(r"[ニハ](?=丁目|番|号)")
ADDRESS_NUMERAL_MAP = {"ニ": "二", "ハ": "八"}

DATE_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?")
CARD_NUMBER_RE = re.compile(r"[A-Z0-9]{2}\s?[0-9OIlSBZ]{8}\s?[A-Z0-9]{2}")
DURATION_RE = re.compile(r"(?:(\d+)\s*年)?\s*(?:(\d+)\s*[ヶか箇ケ]?\s*月)?")

WORK_RESTRICTIONS = [
    "就労不可",
    "就労制限なし",
    "在留資格に基づく就労活動のみ可",
    "指定書により指定された就労活動のみ可",
    "指定書記載機関での在留資格に基づく就労活動のみ可",
]

STATUSES_OF_RESIDENCE = [
    "外交", "公用", "教授", "芸術", "宗教", "報道", "高度専門職1号イ", "高度専門職1号ロ", "高度専門職1号ハ",
    "高度専門職2号", "経営・管理", "法律・会計業務", "医療", "研究", "教育", "技術・人文知識・国際業務",
    "企業内転勤", "介護", "興行", "技能", "特定技能1号", "特定技能2号", "技能実習1号イ", "技能実習1号ロ",
    "技能実習2号イ", "技能実習2号ロ", "技能実習3号イ", "技能実習3号ロ", "文化活動", "短期滞在", "留学", "研修",
    "家族滞在", "特定活動", "永住者", "日本人の配偶者等", "永住者の配偶者等", "定住者",
]

# Common OCR confusions, applied by position inside the card number (2 letters, 8 digits, 2 letters).
TO_DIGIT = str.maketrans({"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "l": "1", "S": "5", "B": "8", "Z": "2"})
TO_LETTER = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"})


def normalize(text: str) -> str:
    """NFKC turns full-width digits/letters/brackets into ASCII, which the regexes expect."""
    return unicodedata.normalize("NFKC", text).translate(CONFUSABLES).strip()
