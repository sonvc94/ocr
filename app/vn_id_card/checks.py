"""Card-level judgements: OCR quality, and consistency between the ID number, birth date, sex and expiry."""

from __future__ import annotations

from datetime import date

from ..card_core import quality
from ..card_core.field import Field
from ..card_core.layout import Document
from .fields import FIELD_KEYS, NO_EXPIRY
from .patterns import CENTURY_SEX_DIGIT, PROVINCE_CODES, RENEWAL_AGES


def assess_quality(doc: Document, vi_labels_found: int, design: str) -> dict:
    return quality.assess_quality(doc, vi_labels_found, len(FIELD_KEYS[design]), "tiếng Việt")


def _date(f: Field) -> date | None:
    try:
        return date.fromisoformat(f.value) if f.value else None
    except ValueError:
        return None


def _birthday_at(dob: date, age: int) -> set[date]:
    if (dob.month, dob.day) == (2, 29):
        return {date(dob.year + age, 2, 28), date(dob.year + age, 3, 1)} | (
            {date(dob.year + age, 2, 29)} if (dob.year + age) % 4 == 0 else set()
        )
    return {date(dob.year + age, dob.month, dob.day)}


def cross_check(fields: dict[str, Field], design: str) -> list[str]:
    """The personal identification number encodes where the birth was registered (digits 1–3), century of
    birth + sex (digit 4) and birth year (digits 5–6); the card expires on the birthday at a renewal age."""
    warnings = []
    number, sex = fields["id_number"].value, fields["sex"].value
    dob = _date(fields["date_of_birth"])
    expiry = None if fields["date_of_expiry"].value == NO_EXPIRY else _date(fields["date_of_expiry"])

    if number:
        if len(number) != 12 or not number.isdigit():
            warnings.append("Số định danh cá nhân phải gồm đúng 12 chữ số.")
            fields["id_number"].needs_review = True
        else:
            if number[:3] not in PROVINCE_CODES:
                warnings.append(f"3 số đầu ({number[:3]}) không phải mã tỉnh/thành nơi đăng ký khai sinh.")
                fields["id_number"].needs_review = True
            if dob:
                expected = CENTURY_SEX_DIGIT.get((dob.year // 100 * 100, sex)) if sex else None
                if expected and number[3] != expected:
                    warnings.append(f"Số thứ 4 của số định danh ({number[3]}) không khớp giới tính {sex} / thế kỷ sinh {dob.year // 100 + 1}.")
                    fields["id_number"].needs_review = fields["sex"].needs_review = True
                if number[4:6] != f"{dob.year % 100:02d}":
                    warnings.append(f"Số thứ 5–6 của số định danh ({number[4:6]}) không khớp năm sinh {dob.year}.")
                    fields["id_number"].needs_review = fields["date_of_birth"].needs_review = True

    if dob and dob > date.today():
        warnings.append("Ngày sinh ở tương lai.")
        fields["date_of_birth"].needs_review = True
    if dob and expiry:
        if not any(expiry in _birthday_at(dob, age) for age in RENEWAL_AGES[design]):
            ages = "/".join(map(str, RENEWAL_AGES[design]))
            warnings.append(f"Ngày hết hạn không trùng sinh nhật tuổi {ages} (thẻ hết hạn vào các mốc này).")
            fields["date_of_expiry"].needs_review = True
    if expiry and expiry < date.today():
        warnings.append("Thẻ đã hết hạn.")
    return warnings
