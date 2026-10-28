"""Extraction of each field's value from the card text, given where the labels were found."""

from __future__ import annotations

import difflib
import re
from datetime import date

from ..card_core.field import Field
from ..card_core.field import finish as _finish
from ..card_core.field import snap as _snap
from ..card_core.layout import Document
from .patterns import (
    ADDRESS_NUMERAL_FIX,
    ADDRESS_NUMERAL_MAP,
    CARD_NUMBER_RE,
    CJK_RE,
    DATE_RE,
    DURATION_RE,
    ENGLISH_SUBLABELS,
    LABELS,
    NOISE,
    PERMISSION_TYPE_RE,
    STATUSES_OF_RESIDENCE,
    TO_DIGIT,
    TO_LETTER,
    WORK_RESTRICTIONS,
)

Labels = dict[str, tuple[int, int]]  # label key -> (start, end) in Document.text


def label_positions(text: str) -> Labels:
    found: Labels = {}
    for key, pattern in LABELS.items():
        m = re.search(pattern, text)
        if m:
            found[key] = (m.start(), m.end())
    return found


def extract_fields(doc: Document, labels: Labels) -> tuple[dict[str, Field], set[str]]:
    """All 15 fields, in output order, and the keys found without a label (by pattern only)."""
    guessed: set[str] = set()
    fields = {"card_number": _card_number(doc), "name": _name(doc, labels)}
    for key in ("date_of_birth", "permission_date", "issue_date"):
        fields[key] = _labeled_date(doc, labels, key)
    fields["sex"] = _sex(doc, labels)
    for key in ("nationality", "address", "status_of_residence"):
        fields[key] = _free_text(doc, labels, key)
    fields["work_restriction"], found_by_pattern = _work_restriction(doc, labels)
    if found_by_pattern:
        guessed.add("work_restriction")
    fields["period_of_stay"], fields["expiration_date"] = _period_of_stay(doc, labels)
    fields["permission_type"], fields["issuing_authority"], found_by_pattern = _permission(doc, labels)
    if found_by_pattern:
        guessed.add("permission_type")
    if fields["permission_date"].value is None and fields["issue_date"].value is None:
        unlabeled = _unlabeled_permission_dates(doc)
        fields |= unlabeled
        guessed |= unlabeled.keys()
    fields["valid_until"] = _valid_until(doc)
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


def _fix_card_number(raw: str) -> str:
    s = re.sub(r"\s", "", raw).upper()
    if len(s) != 12:
        return s
    return s[:2].translate(TO_LETTER) + s[2:10].translate(TO_DIGIT) + s[10:].translate(TO_LETTER)


def _card_number(doc: Document) -> Field:
    """Searched everywhere: it is the most distinctive pattern on the card."""
    f = Field()
    m = CARD_NUMBER_RE.search(doc.text.upper())
    if m:
        f.raw = m.group(0)
        fixed = _fix_card_number(f.raw)
        f.value = fixed
        if not re.fullmatch(r"[A-Z]{2}\d{8}[A-Z]{2}", fixed):
            f.notes.append("Sai định dạng số thẻ (2 chữ + 8 số + 2 chữ).")
        elif fixed != re.sub(r"\s", "", f.raw.upper()):
            f.notes.append("Đã tự sửa ký tự dễ nhầm (O/0, I/1...).")
    return _finish(f, doc.score(m.start(), m.end()) if m else None)


def _name(doc: Document, labels: Labels) -> Field:
    """Latin uppercase part after 氏名."""
    f = Field()
    seg = _segment(doc, labels, "name")
    if not seg:
        return _finish(f, None)
    raw, a, b = seg
    f.raw = _clean(raw)
    latin = re.findall(r"[A-Z][A-Z ,.'\-]*[A-Z.]", ENGLISH_SUBLABELS.sub(" ", raw.upper()))
    f.value = max(latin, key=len).strip() if latin else (f.raw or None)
    return _finish(f, doc.score(a, b))


def _labeled_date(doc: Document, labels: Labels, key: str) -> Field:
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
    return _finish(f, conf)


def _sex(doc: Document, labels: Labels) -> Field:
    """男/女 or M./F. — may sit in its own segment or in the date-of-birth row."""
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
    return _finish(f, conf)


def _free_text(doc: Document, labels: Labels, key: str) -> Field:
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
    return _finish(f, conf)


def _work_restriction(doc: Document, labels: Labels) -> tuple[Field, bool]:
    """Snapped to the closest official wording. Also returns whether it was found without its label."""
    f = Field()
    seg = _segment(doc, labels, "work_restriction")
    if seg:
        raw, a, b = seg
        f.raw = _clean(raw)
        _snap(f, re.sub(r"\s", "", f.raw), WORK_RESTRICTIONS)
        return _finish(f, doc.score(a, b)), False
    # No label: look for a box whose whole text is close to one of the official values.
    for a, b, _ in doc.spans:
        chunk = doc.text[a:b]
        if difflib.get_close_matches(re.sub(r"\s", "", chunk), WORK_RESTRICTIONS, n=1, cutoff=0.6):
            f.raw = chunk
            _snap(f, re.sub(r"\s", "", chunk), WORK_RESTRICTIONS)
            return _finish(f, doc.score(a, b)), True
    return _finish(f, None), False


def _period_of_stay(doc: Document, labels: Labels) -> tuple[Field, Field]:
    """Duration + expiration date in parentheses."""
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
    return _finish(f_period, conf_p), _finish(f_exp, conf_e)


def _permission(doc: Document, labels: Labels) -> tuple[Field, Field, bool]:
    """Permission type + issuing authority in parentheses, e.g. 在留期間更新許可(東京出入国在留管理局長).
    Also returns whether the type was found without its label."""
    f_type, f_auth = Field(), Field()
    seg = _segment(doc, labels, "permission_type")
    conf = None
    guessed = False
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
    elif m := PERMISSION_TYPE_RE.search(doc.text):
        f_type.raw = f_type.value = m.group(0)
        conf = doc.score(m.start(), m.end())
        guessed = True
    return _finish(f_type, conf), _finish(f_auth, conf if f_auth.value else None), guessed


def _unlabeled_permission_dates(doc: Document) -> dict[str, Field]:
    """Both date labels unreadable: two dates side by side (not followed by まで) are permission + issue date."""
    m = re.search(DATE_RE.pattern + r"[^\n\d]{0,10}?" + DATE_RE.pattern + r"(?!\s*まで)", doc.text)
    if not m:
        return {}
    found = {}
    for key, part in (("permission_date", 0), ("issue_date", 1)):
        dm = list(DATE_RE.finditer(m.group(0)))[part]
        f = Field(raw=dm.group(0))
        f.value, _ = _parse_date(dm.group(0))
        found[key] = _finish(f, doc.score(m.start() + dm.start(), m.start() + dm.end()))
    return found


def _valid_until(doc: Document) -> Field:
    """The sentence このカードは YYYY年MM月DD日まで有効です。 (効 is often cut off)."""
    f = Field()
    conf = None
    m = re.search(DATE_RE.pattern + r"\s*まで\s*有", doc.text)
    if m:
        f.raw = m.group(0)
        f.value, _ = _parse_date(m.group(0))
        conf = doc.score(m.start(), m.end())
    return _finish(f, conf)
