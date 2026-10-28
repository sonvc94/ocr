"""Extraction of each field's value from the card text, given where the labels were found."""

from __future__ import annotations

import difflib
import re
from datetime import date

from ..card_core.field import Field, finish
from ..card_core.layout import Document
from .patterns import (
    DATE_RE,
    ENGLISH_SUBLABELS,
    ID_NUMBER_RE,
    LABELS,
    NATIONALITIES,
    NO_EXPIRY_RE,
    SEXES,
    TO_DIGIT,
    VI_LABELS,
    fold,
    foreign_letters,
)

Labels = dict[str, tuple[int, int]]  # label key -> (start, end) in Document.text
_COMMON = ("id_number", "full_name", "date_of_birth", "sex", "nationality", "date_of_expiry")
FIELD_KEYS = {"2024": _COMMON, "cccd_2021": _COMMON + ("place_of_origin", "place_of_residence")}
NO_EXPIRY = "Không thời hạn"
_DATE_LABEL_TAIL = re.compile(r"(?<![^\W\d_])(?:[^\W\d_]+\s*){1,4}:\s*$")


def label_positions(text: str, design: str) -> tuple[Labels, set[str]]:
    """Where each label is, and the keys whose Vietnamese label was readable (not just the English one)."""
    found: Labels = {}
    vietnamese: set[str] = set()
    for key, pattern in LABELS[design].items():
        m = pattern.search(text)
        if m:
            found[key] = (m.start(), m.end())
            if VI_LABELS[design][key].match(text, m.start()):
                vietnamese.add(key)
    return found, vietnamese


def extract_fields(doc: Document, labels: Labels, design: str) -> tuple[dict[str, Field], set[str]]:
    """All fields of the design, in output order, and the keys found without a label (by pattern only)."""
    guessed: set[str] = set()
    fields = {}
    fields["id_number"], by_pattern = _id_number(doc, labels)
    if by_pattern:
        guessed.add("id_number")
    fields["full_name"] = _full_name(doc, labels)
    dob, dob_span = _labeled_date(doc, labels, "date_of_birth")
    exp, exp_span = _expiry(doc, labels, dob_span)
    # Labels unreadable: of the dates left over, the earliest is the birth date and the latest the expiry.
    used = {s for s in (dob_span, exp_span) if s}
    left = sorted((_iso(m), m.span()) for m in DATE_RE.finditer(doc.text) if m.span() not in used and _iso(m))
    if dob.value is None and "date_of_birth" not in labels and left:
        dob = _date_field(doc, *left.pop(0))
        guessed.add("date_of_birth")
    if exp.value is None and "date_of_expiry" not in labels and left:
        exp = _date_field(doc, *left.pop())
        guessed.add("date_of_expiry")
    fields["date_of_birth"] = dob
    fields["sex"] = _sex(doc, labels)
    fields["nationality"] = _nationality(doc, labels)
    fields["date_of_expiry"] = exp
    if "place_of_origin" in FIELD_KEYS[design]:
        skip = [s for s in (dob_span, exp_span) if s]
        fields["place_of_origin"] = _place(doc, labels, "place_of_origin", design, skip, to_end=False)
        # printed last, over two rows; the expiry block (left of it, under the photo) often lands in between
        fields["place_of_residence"] = _place(doc, labels, "place_of_residence", design, skip, to_end=True)
    return fields, guessed


def _segment(doc: Document, labels: Labels, key: str) -> tuple[str, int, int] | None:
    """Text between `key`'s label and the nearest following label (or end of text)."""
    if key not in labels:
        return None
    start = labels[key][1]
    following = [s for s, _ in labels.values() if s >= start]
    end = min(following, default=len(doc.text))
    return doc.text[start:end], start, end


def _clean(value: str) -> str:
    value = ENGLISH_SUBLABELS.sub(" ", value)
    value = re.sub(r"[ \t]+", " ", value.replace("\n", " "))
    return value.strip(" :;/.,-")


def _iso(m: re.Match) -> str | None:
    d, mo, y = (int(g) for g in m.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _date_field(doc: Document, iso: str, span: tuple[int, int]) -> Field:
    f = Field(value=iso, raw=doc.text[span[0]:span[1]])
    return finish(f, doc.score(*span))


def _id_number(doc: Document, labels: Labels) -> tuple[Field, bool]:
    """12 digits after its label; anywhere on the card when the label is unreadable."""
    f = Field()
    seg = _segment(doc, labels, "id_number")
    m, offset, by_pattern = None, 0, False
    if seg:
        m, offset = ID_NUMBER_RE.search(seg[0]), seg[1]
    if m is None:
        m, offset, by_pattern = ID_NUMBER_RE.search(doc.text), 0, True
    if m is None:
        return finish(f, None), False
    f.raw = m.group(0)
    compact = re.sub(r"\s", "", f.raw)
    f.value = compact.translate(TO_DIGIT)
    if f.value != compact:
        f.notes.append("Đã tự sửa ký tự dễ nhầm (O/0, I/1...).")
    return finish(f, doc.score(offset + m.start(), offset + m.end())), by_pattern


def _full_name(doc: Document, labels: Labels) -> Field:
    """The longest run of uppercase words after the label (the name is printed in capitals)."""
    f = Field()
    seg = _segment(doc, labels, "full_name")
    if not seg:
        return finish(f, None)
    raw, a, b = seg
    f.raw = _clean(raw)
    runs: list[list[str]] = [[]]
    for word in re.findall(r"[^\W\d_]+", f.raw):
        if word.isupper():
            runs[-1].append(word)
        elif runs[-1]:
            runs.append([])
    best = max(runs, key=len)
    if best:
        f.value = " ".join(best)
        if odd := foreign_letters(f.value):
            f.notes.append(f"Có chữ không dùng trong tiếng Việt ({''.join(dict.fromkeys(odd))}): OCR đọc sai dấu.")
    elif f.raw:
        f.value = f.raw
        f.notes.append("Tên không in hoa như trên thẻ, có thể đọc nhầm.")
    return finish(f, doc.score(a, b))


def _labeled_date(doc: Document, labels: Labels, key: str) -> tuple[Field, tuple[int, int] | None]:
    f = Field()
    seg = _segment(doc, labels, key)
    if seg:
        m = DATE_RE.search(seg[0])
        if m:
            span = (seg[1] + m.start(), seg[1] + m.end())
            f.raw, f.value = m.group(0), _iso(m)
            if f.value is None:
                f.notes.append("Ngày không hợp lệ.")
            return finish(f, doc.score(*span)), span
    return finish(f, None), None


def _expiry(doc: Document, labels: Labels, dob_span: tuple[int, int] | None) -> tuple[Field, tuple[int, int] | None]:
    """Printed under its label, below the photo: the row holding the label also holds sex and nationality,
    so the date usually comes after them. Taken as the first date after the label that is not the birth date."""
    f, span = _labeled_date(doc, labels, "date_of_expiry")
    if f.value or "date_of_expiry" not in labels:
        return f, span
    start = labels["date_of_expiry"][1]
    if m := NO_EXPIRY_RE.search(doc.text, start):
        f.raw, f.value = m.group(0), NO_EXPIRY
        return finish(f, doc.score(m.start(), m.end())), None
    for m in DATE_RE.finditer(doc.text, start):
        if m.span() != dob_span:
            return _found_date(doc, f, m)
    # Only the English half "Date of expiry" was readable: it is printed under the label and its date.
    label = labels["date_of_expiry"][0]
    before = [m for m in DATE_RE.finditer(doc.text, 0, label) if m.span() != dob_span]
    if before and doc.text.count("\n", before[-1].end(), label) <= 1:  # same row or the row above
        return _found_date(doc, f, before[-1])
    return f, None


def _found_date(doc: Document, f: Field, m: re.Match) -> tuple[Field, tuple[int, int]]:
    f.raw, f.value = m.group(0), _iso(m)
    if f.value is None:
        f.notes.append("Ngày không hợp lệ.")
    return finish(f, doc.score(*m.span())), m.span()


def _sex(doc: Document, labels: Labels) -> Field:
    f = Field()
    seg = _segment(doc, labels, "sex")
    if seg:
        raw, a, _ = seg
        for m in re.finditer(r"[^\W\d_]+", raw):
            if fold(m.group(0)) in SEXES:  # only two values: the letters decide, diacritics are restored
                f.raw, f.value = m.group(0), SEXES[fold(m.group(0))]
                return finish(f, doc.score(a + m.start(), a + m.end()))
    return finish(f, None)


def _nationality(doc: Document, labels: Labels) -> Field:
    f = Field()
    seg = _segment(doc, labels, "nationality")
    if not seg:
        return finish(f, None)
    raw, a, b = seg
    # the segment may run on into the expiry date printed on the next row
    f.raw = _clean(DATE_RE.sub(" ", raw)).strip(" 0123456789")
    best = difflib.get_close_matches(fold(f.raw), [fold(n) for n in NATIONALITIES], n=1, cutoff=0.6)
    if best:
        f.value = next(n for n in NATIONALITIES if fold(n) == best[0])
        if fold(f.value) != fold(f.raw):  # diacritics alone ("Viêt Nam") are restored without a flag
            f.notes.append("Đã chuẩn hoá theo danh sách giá trị chính thức.")
    else:
        f.value = f.raw or None
    return finish(f, doc.score(a, b))


def _place(doc: Document, labels: Labels, key: str, design: str, skip: list[tuple[int, int]], to_end: bool) -> Field:
    """Address text after the label: up to the next label, or (`to_end`) to the end of the card text with
    every other label and the dates taken out. Diacritics are left as read: there is no list to check them against."""
    f = Field()
    if key not in labels:
        return finish(f, None)
    start = labels[key][1]
    end = len(doc.text) if to_end else _segment(doc, labels, key)[2]
    cut = [(m.start(), m.end()) for p in LABELS[design].values() for m in p.finditer(doc.text, start, end)]
    dates = [m.span() for m in DATE_RE.finditer(doc.text, start, end)] + [sp for sp in skip if start <= sp[0] < end]
    for a, _ in dates:  # a garbled label of that date ("Co gia ey dèn: 04/11/2031"): up to 4 words and a colon
        head = max(doc.text.rfind("\n", start, a) + 1, start)
        if m := _DATE_LABEL_TAIL.search(doc.text, head, a):
            cut.append((m.start(), a))
    cut += dates
    keep = [i for i in range(start, end) if not any(a <= i < b for a, b in cut)]
    text = "".join(doc.text[i] for i in keep)
    f.raw = _clean(text)
    f.value = re.sub(r"\s*,\s*", ", ", f.raw).strip(" ,") or None
    scores = [sc for i in keep if not doc.text[i].isspace() and (sc := doc.score(i, i + 1)) is not None]
    return finish(f, min(scores, default=None))
