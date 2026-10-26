"""Rule-based field extraction for the front side of a Japanese residence card (在留カード).

Input is the list of OCR text boxes (text, score, box). Boxes are grouped into visual
rows, joined into one normalized text, and each field is taken as the span between
its label and the next label found on the card.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

CONFIDENCE_THRESHOLD = 0.85


@dataclass
class OcrBox:
    text: str
    score: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2
    virtual: bool = False  # label inserted by the parser, not read by OCR

    @property
    def cy(self) -> float:
        return (self.box[1] + self.box[3]) / 2

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]


@dataclass
class Field:
    value: str | None = None
    raw: str | None = None
    confidence: float | None = None
    needs_review: bool = True
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "raw": self.raw,
            "confidence": None if self.confidence is None else round(self.confidence, 4),
            "needs_review": self.needs_review,
            "notes": self.notes,
        }


# Label patterns, in the order they appear on the card. Negative lookaheads keep a label
# from matching inside a value (e.g. "在留期間更新許可" is a permission type, not a label).
LABELS: dict[str, str] = {
    "card_number": r"番号",
    "name": r"氏\s*名",
    "date_of_birth": r"生\s*年\s*月\s*日",
    "sex": r"性\s*別",
    "nationality": r"国\s*籍\s*[・･·]?\s*(?:地\s*[域城])?|国\s*[・･·]\s*地\s*[域城]",
    "address": r"住\s*居\s*地",
    "status_of_residence": r"在\s*留\s*資\s*格(?!に基づく|変更)",
    "work_restriction": r"就\s*労\s*制\s*限\s*(?:の\s*)?有\s*無",
    "period_of_stay": r"在\s*留\s*期\s*間(?!更新)\s*(?:[(（]\s*満\s*了\s*日\s*[)）])?",
    "permission_type": r"許\s*可\s*(?:の\s*)?種\s*類",
    "permission_date": r"許\s*可\s*年\s*月\s*日",
    "issue_date": r"交\s*付\s*年\s*月\s*日",
    "valid_until_marker": r"この\s*カ\s*[ー一-]?\s*ド\s*は",
}

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
PERMISSION_TYPE_RE = re.compile(r"(?:在留期間更新|在留資格変更|在留資格取得|永住|上陸)許可")
CJK_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")

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


def group_rows(boxes: list[OcrBox]) -> list[list[OcrBox]]:
    """Group boxes whose vertical centers fall on the same line, left to right inside each row."""
    rows: list[list[OcrBox]] = []
    for b in sorted(boxes, key=lambda b: b.cy):
        if rows:
            last = rows[-1]
            ref_cy = sum(x.cy for x in last) / len(last)
            ref_h = min(min(x.height for x in last), b.height)
            if abs(b.cy - ref_cy) < ref_h * 0.5:
                last.append(b)
                continue
        rows.append([b])
    return [sorted(r, key=lambda b: b.box[0]) for r in rows]


class _Document:
    """Flattened card text with a char-span -> OCR score mapping for confidence lookup."""

    def __init__(self, boxes: list[OcrBox]):
        self.rows = group_rows(boxes)
        parts: list[str] = []
        self.spans: list[tuple[int, int, float]] = []
        self.ocr_scores = [b.score for b in boxes if not b.virtual]
        pos = 0
        for r_idx, row in enumerate(self.rows):
            if r_idx:
                parts.append("\n")
                pos += 1
            for b_idx, b in enumerate(row):
                if b_idx:
                    parts.append(" ")
                    pos += 1
                t = normalize(b.text)
                parts.append(t)
                if not b.virtual:
                    self.spans.append((pos, pos + len(t), b.score))
                pos += len(t)
        self.text = "".join(parts)

    def score(self, start: int, end: int) -> float | None:
        scores = [s for a, b, s in self.spans if a < end and b > start]
        return min(scores) if scores else None

    @property
    def mean_score(self) -> float | None:
        return sum(self.ocr_scores) / len(self.ocr_scores) if self.ocr_scores else None


def _anchor_labels(boxes: list[OcrBox], missing: list[str]) -> tuple[list[OcrBox], set[str]]:
    """Put a canonical Japanese label where an unreadable one sits, using the English sub-label below it.

    The box directly above the English sub-label (same left edge) is taken to be the garbled
    Japanese label and its text is replaced; if there is none, a virtual label box is inserted
    on the value's row.
    """
    boxes = list(boxes)
    anchored: set[str] = set()
    for key in missing:
        pattern, label = ENGLISH_ANCHORS[key]
        anchor = next((b for b in boxes if re.search(pattern, normalize(b.text).upper())), None)
        if anchor is None:
            continue
        x1, y1, x2, _ = anchor.box
        h = anchor.height
        above = [
            (i, b) for i, b in enumerate(boxes)
            if b is not anchor and abs(b.box[0] - x1) < 1.5 * h and b.box[3] <= y1 + 0.5 * h
            and y1 - b.box[3] < 1.5 * h and len(b.text) <= 10 and not re.search(r"[A-Z]{3}", b.text)
            and not DATE_RE.search(normalize(b.text))
        ]
        if above:
            i, b = max(above, key=lambda ib: ib[1].box[3])
            boxes[i] = OcrBox(label, b.score, b.box, virtual=True)
        else:
            boxes.append(OcrBox(label, 1.0, (x1, y1 - 1.2 * h, x1 + h, y1 - 0.2 * h), virtual=True))
        anchored.add(key)
    return boxes, anchored


def _label_positions(text: str) -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    for key, pattern in LABELS.items():
        m = re.search(pattern, text)
        if m:
            found[key] = (m.start(), m.end())
    return found


def _segment(doc: _Document, labels: dict[str, tuple[int, int]], key: str) -> tuple[str, int, int] | None:
    """Text between `key`'s label and the nearest following label (or end of text)."""
    if key not in labels:
        return None
    start = labels[key][1]
    following = [s for s, _ in labels.values() if s >= start]
    end = min(following, default=len(doc.text))
    return doc.text[start:end], start, end


def _clean(value: str) -> str:
    value = NOISE.sub(" ", ENGLISH_SUBLABELS.sub(" ", value))
    value = re.sub(r"[ \t]+", " ", value.replace("\n", " "))
    return value.strip(" :：/・·")


def _parse_date(text: str) -> tuple[str | None, re.Match | None]:
    m = DATE_RE.search(text)
    if not m:
        return None, None
    y, mo, d = (int(g) for g in m.groups())
    try:
        return date(y, mo, d).isoformat(), m
    except ValueError:
        return None, m


def _finish(f: Field, confidence: float | None) -> Field:
    f.confidence = confidence
    f.needs_review = f.value is None or confidence is None or confidence < CONFIDENCE_THRESHOLD or bool(f.notes)
    return f


def _snap(f: Field, text: str, choices: list[str]) -> None:
    """Set f.value to the closest official wording; flag it when OCR text had to be corrected."""
    best = difflib.get_close_matches(text, choices, n=1, cutoff=0.6)
    if best:
        f.value = best[0]
        if best[0] != text:
            f.notes.append("Đã chuẩn hoá theo danh sách giá trị chính thức.")
    else:
        f.value = text or None


def _fix_card_number(raw: str) -> str:
    s = re.sub(r"\s", "", raw).upper()
    if len(s) != 12:
        return s
    return s[:2].translate(TO_LETTER) + s[2:10].translate(TO_DIGIT) + s[10:].translate(TO_LETTER)


def _drop_non_text(boxes: list[OcrBox]) -> list[OcrBox]:
    """Text lines on the card are all about the same height; a box several times taller is the photo or a seal."""
    if len(boxes) < 5:
        return boxes
    median_h = sorted(b.height for b in boxes)[len(boxes) // 2]
    return [b for b in boxes if b.height <= 4 * median_h]


def _card_design(text: str, labels: dict) -> str:
    if re.search(r"個\s*人\s*番?\s*号?|特\s*定\s*在\s*留", text):
        return "specified_2026"  # 特定在留カード (residence card + My Number card), different layout
    no_permission_rows = "permission_type" not in labels and "issue_date" not in labels
    if re.search(r"\bISA\b", text) or (no_permission_rows and re.search(r"在\s*留\s*期\s*間\s*満", text)):
        return "2026"
    return "2012"


def parse_residence_card(boxes: list[OcrBox]) -> dict:
    boxes = _drop_non_text(boxes)
    ocr_doc = _Document(boxes)
    labels = _label_positions(ocr_doc.text)
    jp_labels_found = len(labels.keys() - {"card_number", "valid_until_marker"})
    missing = [k for k in ENGLISH_ANCHORS if k not in labels]
    anchored: set[str] = set()
    if missing:
        boxes, anchored = _anchor_labels(boxes, missing)
    doc = _Document(boxes) if anchored else ocr_doc
    text = doc.text
    labels = _label_positions(text)
    fields: dict[str, Field] = {}
    guessed: set[str] = set()  # fields found without any label, by pattern only
    warnings: list[str] = []

    if not re.search(r"在\s*留\s*カ\s*[ー一-]?\s*ド|RESIDENCE\s*CARD", text, re.IGNORECASE):
        warnings.append("Không tìm thấy chữ 在留カード / RESIDENCE CARD — ảnh có thể không phải thẻ cư trú.")

    # Card number: search everywhere, it is the most distinctive pattern on the card.
    f = Field()
    m = CARD_NUMBER_RE.search(text.upper())
    if m:
        f.raw = m.group(0)
        fixed = _fix_card_number(f.raw)
        f.value = fixed
        if not re.fullmatch(r"[A-Z]{2}\d{8}[A-Z]{2}", fixed):
            f.notes.append("Sai định dạng số thẻ (2 chữ + 8 số + 2 chữ).")
        elif fixed != re.sub(r"\s", "", f.raw.upper()):
            f.notes.append("Đã tự sửa ký tự dễ nhầm (O/0, I/1...).")
    fields["card_number"] = _finish(f, doc.score(m.start(), m.end()) if m else None)

    # Name: Latin uppercase part after 氏名.
    f = Field()
    seg = _segment(doc, labels, "name")
    if seg:
        raw, a, b = seg
        f.raw = _clean(raw)
        latin = re.findall(r"[A-Z][A-Z ,.'\-]*[A-Z.]", ENGLISH_SUBLABELS.sub(" ", raw.upper()))
        f.value = max(latin, key=len).strip() if latin else (f.raw or None)
        fields["name"] = _finish(f, doc.score(a, b))
    else:
        fields["name"] = _finish(f, None)

    # Date fields.
    for key in ("date_of_birth", "permission_date", "issue_date"):
        f = Field()
        seg = _segment(doc, labels, key)
        conf = None
        if seg:
            raw, a, b = seg
            iso, dm = _parse_date(raw)
            if dm:
                f.raw = dm.group(0)
                f.value = iso
                conf = doc.score(a + dm.start(), a + dm.end())
                if iso is None:
                    f.notes.append("Ngày không hợp lệ.")
        fields[key] = _finish(f, conf)

    # Sex: 男/女 or M./F. — may sit in its own segment or in the date-of-birth row.
    f = Field()
    conf = None
    for key in ("sex", "date_of_birth"):
        seg = _segment(doc, labels, key)
        if not seg:
            continue
        raw, a, b = seg
        m = re.search(r"男|女|\bM\b\.?|\bF\b\.?", raw)
        if m:
            f.raw = m.group(0)
            f.value = "M" if m.group(0) in ("男",) or m.group(0).startswith("M") else "F"
            conf = doc.score(a + m.start(), a + m.end())
            break
    fields["sex"] = _finish(f, conf)

    # Free-text fields.
    for key in ("nationality", "address", "status_of_residence"):
        f = Field()
        seg = _segment(doc, labels, key)
        conf = None
        if seg:
            raw, a, b = seg
            f.raw = _clean(raw)
            value = f.raw
            if key == "address":
                value = ADDRESS_NUMERAL_FIX.sub(lambda m: ADDRESS_NUMERAL_MAP[m.group(0)], value)
            if key == "nationality":
                # printed in Japanese only; Latin text here is a stray sub-label (e.g. "D SEX" read as "DSEX")
                value = re.sub(r"\s+", " ", re.sub(r"[A-Za-z][A-Za-z./]*", " ", value)).strip()
                if not CJK_RE.search(value):
                    value = ""
            if key == "status_of_residence":
                # drop the English translation printed next to it (e.g. "留学 College Student")
                _snap(f, re.sub(r"[A-Za-z\s]", "", value), STATUSES_OF_RESIDENCE)
            else:
                f.value = value or None
            conf = doc.score(a, b)
        fields[key] = _finish(f, conf)

    # Work restriction: snap to the closest official wording.
    f = Field()
    seg = _segment(doc, labels, "work_restriction")
    conf = None
    if seg:
        raw, a, b = seg
        f.raw = _clean(raw)
        _snap(f, re.sub(r"\s", "", f.raw), WORK_RESTRICTIONS)
        conf = doc.score(a, b)
    else:
        # No label: look for a box whose whole text is close to one of the official values.
        for a, b, _ in doc.spans:
            chunk = doc.text[a:b]
            if difflib.get_close_matches(re.sub(r"\s", "", chunk), WORK_RESTRICTIONS, n=1, cutoff=0.6):
                f.raw = chunk
                _snap(f, re.sub(r"\s", "", chunk), WORK_RESTRICTIONS)
                conf = doc.score(a, b)
                guessed.add("work_restriction")
                break
    fields["work_restriction"] = _finish(f, conf)

    # Period of stay: duration + expiration date in parentheses.
    f_period, f_exp = Field(), Field()
    seg = _segment(doc, labels, "period_of_stay")
    conf_p = conf_e = None
    if seg:
        raw, a, b = seg
        dm = DATE_RE.search(raw)
        f_period.raw = _clean(raw[: dm.end() + 1] if dm else raw)  # stop at "(満了日)" when later labels are unreadable
        head = raw[: dm.start()] if dm else raw
        dur = next((m for m in DURATION_RE.finditer(head) if m.group(0).strip()), None)
        if dur:
            years, months = dur.group(1), dur.group(2)
            f_period.value = (f"{years}年" if years else "") + (f"{months}月" if months else "")
            conf_p = doc.score(a + dur.start(), a + dur.end())
        if dm:
            iso, _ = _parse_date(dm.group(0))
            f_exp.raw, f_exp.value = dm.group(0), iso
            conf_e = doc.score(a + dm.start(), a + dm.end())
    fields["period_of_stay"] = _finish(f_period, conf_p)
    fields["expiration_date"] = _finish(f_exp, conf_e)

    # Permission type + issuing authority in parentheses, e.g. 在留期間更新許可(東京出入国在留管理局長).
    f_type, f_auth = Field(), Field()
    seg = _segment(doc, labels, "permission_type")
    conf = None
    if seg:
        raw, a, b = seg
        cleaned = _clean(raw)
        f_type.raw = cleaned
        m = re.match(r"([^()]*)\(([^()]*)\)?", cleaned)
        if m:
            f_type.value = m.group(1).strip() or None
            f_auth.value = m.group(2).strip() or None
            f_auth.raw = m.group(2)
        else:
            f_type.value = cleaned or None
        conf = doc.score(a, b)
    elif m := PERMISSION_TYPE_RE.search(text):
        f_type.raw = f_type.value = m.group(0)
        conf = doc.score(m.start(), m.end())
        guessed.add("permission_type")
    fields["permission_type"] = _finish(f_type, conf)
    fields["issuing_authority"] = _finish(f_auth, conf if f_auth.value else None)

    if fields["permission_date"].value is None and fields["issue_date"].value is None:
        m = re.search(DATE_RE.pattern + r"[^\n\d]{0,10}?" + DATE_RE.pattern + r"(?!\s*まで)", text)
        if m:
            for key, part in (("permission_date", 0), ("issue_date", 1)):
                dm = list(DATE_RE.finditer(m.group(0)))[part]
                f = Field(raw=dm.group(0))
                f.value, _ = _parse_date(dm.group(0))
                fields[key] = _finish(f, doc.score(m.start() + dm.start(), m.start() + dm.end()))
                guessed.add(key)

    # "このカードは YYYY年MM月DD日まで有効です。" (効 is often cut off)
    f = Field()
    conf = None
    m = re.search(DATE_RE.pattern + r"\s*まで\s*有", text)
    if m:
        f.raw = m.group(0)
        f.value, _ = _parse_date(m.group(0))
        conf = doc.score(m.start(), m.end())
    fields["valid_until"] = _finish(f, conf)

    design = _card_design(text, labels)
    if design == "2026":
        for key in NOT_PRINTED_SINCE_2026:
            fields[key] = Field(notes=["Mẫu thẻ từ 14/06/2026 không in mục này (chỉ lưu trong chip IC)."], needs_review=False)
            guessed.discard(key)
    elif design == "specified_2026":
        warnings.append("Đây là 特定在留カード (thẻ cư trú gộp My Number), bố cục khác hẳn — demo chưa hỗ trợ, kết quả không đáng tin.")

    derived_from = {"expiration_date": "period_of_stay", "issuing_authority": "permission_type"}
    for key, f in fields.items():
        if f.value is None:
            continue
        if derived_from.get(key, key) in anchored:
            f.notes.append("Nhãn tiếng Nhật đọc lỗi, vị trí xác định qua nhãn tiếng Anh.")
            f.needs_review = True
        if derived_from.get(key, key) in guessed:
            f.notes.append("Không thấy nhãn, đoán theo mẫu chữ.")
            f.needs_review = True

    quality = _assess_quality(ocr_doc, jp_labels_found)
    if design == "specified_2026":
        for f in fields.values():
            f.needs_review = True
    if quality["level"] == "low":
        # Kanji is what breaks first on bad images; never let free-text fields pass silently.
        for key in ("nationality", "address", "status_of_residence", "work_restriction", "permission_type", "issuing_authority"):
            fields[key].needs_review = True

    warnings += _cross_check(fields)

    return {
        "document_type": "residence_card",
        "side": "front",
        "card_design": design,
        "fields": {k: v.to_dict() for k, v in fields.items()},
        "quality": quality,
        "warnings": warnings,
        "mean_ocr_confidence": None if ocr_doc.mean_score is None else round(ocr_doc.mean_score, 4),
        "labels_found": sorted(labels),
        "labels_from_english_anchor": sorted(anchored),
        "full_text": text,
    }


def _assess_quality(doc: _Document, jp_labels_found: int) -> dict:
    """Flag images where OCR clearly struggled, so results are not trusted silently."""
    reasons = []
    expected = len(LABELS) - 2  # card_number and the validity sentence are not field labels
    mean = doc.mean_score
    low_share = sum(s < 0.8 for s in doc.ocr_scores) / len(doc.ocr_scores) if doc.ocr_scores else 1.0
    if mean is None:
        reasons.append("Không đọc được chữ nào trên ảnh.")
    elif mean < 0.9:
        reasons.append(f"Độ tin cậy OCR trung bình thấp ({mean:.2f}).")
    if doc.ocr_scores and low_share > 0.2:
        reasons.append(f"{low_share:.0%} dòng chữ có độ tin cậy dưới 0.8.")
    if jp_labels_found < expected * 0.6:
        reasons.append(f"Chỉ nhận ra {jp_labels_found}/{expected} nhãn tiếng Nhật.")
    return {
        "level": "low" if reasons else "ok",
        "reasons": reasons,
        "advice": "Nên chụp/scan lại rõ hơn (chiều ngang thẻ ≥ 1500px, không lóa, không watermark) hoặc nhập tay các trường cần kiểm tra."
        if reasons else None,
    }


def _cross_check(fields: dict[str, Field]) -> list[str]:
    def d(key: str) -> date | None:
        v = fields[key].value
        return date.fromisoformat(v) if v else None

    warnings = []
    dob, issued, permitted = d("date_of_birth"), d("issue_date"), d("permission_date")
    expires, valid = d("expiration_date"), d("valid_until")
    if dob and issued and dob >= issued:
        warnings.append("Ngày sinh không trước ngày cấp thẻ.")
        fields["date_of_birth"].needs_review = True
    if permitted and issued and permitted > issued:
        warnings.append("Ngày cấp phép sau ngày cấp thẻ.")
    if issued and expires and expires < issued:
        warnings.append("Ngày hết hạn lưu trú trước ngày cấp thẻ.")
        fields["expiration_date"].needs_review = True
    if expires and valid and expires != valid:
        warnings.append("Ngày hết hạn lưu trú khác ngày hết hiệu lực thẻ (bình thường chỉ khác với 永住者).")
    if valid and valid < date.today():
        warnings.append("Thẻ đã hết hiệu lực.")
    return warnings
