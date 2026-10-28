"""What is printed on the front of the Vietnamese identity cards: thẻ căn cước (issued since 01/07/2024) and
the chip Căn cước công dân (2021 design).

Labels are bilingual on one line ("Giới tính / Sex:"); the expiry date sits under the photo. OCR often gets
Vietnamese diacritics wrong, so label patterns accept any diacritic on each letter (`vi_pattern`) and are
matched on the original text: positions stay the same as in the value text (zones.py relies on that).
"""

from __future__ import annotations

import re
import unicodedata


def _variants() -> dict[str, str]:
    """base letter -> every precomposed letter built on it (a -> aàáảãạăằắ...), both cases."""
    out: dict[str, set[str]] = {}
    for cp in range(0x41, 0x1F00):
        c = chr(cp)
        base = unicodedata.normalize("NFD", c)[0]
        if base.isascii() and base.isalpha():
            out.setdefault(base.lower(), set()).update({c, c.lower(), c.upper()})
    out["d"] |= {"đ", "Đ", "Ð"}  # Ð (U+00D0) is a common OCR stand-in for Đ
    return {k: "".join(sorted(v)) for k, v in out.items()}


_VARIANTS = _variants()


# Letters OCR reads in place of another one inside the printed labels ("đjnh" for "định").
_LOOKALIKES = {"i": "jl1"}


def vi_pattern(words: str) -> str:
    """Regex for printed words, tolerant to what OCR does to them: wrong/missing diacritics, dropped spaces
    or commas, a stray letter at the end of a word ("chùr" for "chữ"), ư/ơ read as u'/o' or ur ("thurong").
    Written without diacritics: vi_pattern("gioi tinh") matches "Giới tính", "Gioi tinh", "Giớitính"."""
    out = []
    for c in words:
        if c == " ":
            out.append(r"[^\W\d_]?\s*")
        elif c == ",":
            out.append(r"[,.]?")
        elif c in _VARIANTS:
            out.append(f"[{_VARIANTS[c]}{_LOOKALIKES.get(c, '')}]" + ("['’`r]?" if c in "uo" else ""))
        else:
            out.append(re.escape(c))
    return "".join(out)


def fold(text: str) -> str:
    """Diacritics removed, lowercase ("Việt Nam" -> "viet nam"). Not length-preserving for decomposed input."""
    text = text.replace("đ", "d").replace("Đ", "D").replace("Ð", "D")
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)).lower()


# Marks a Vietnamese letter can carry: tones (grave, acute, tilde, hook, dot below) and circumflex, breve, horn.
_VI_MARKS = {"\u0300", "\u0301", "\u0303", "\u0309", "\u0323", "\u0302", "\u0306", "\u031b"}


def foreign_letters(text: str) -> list[str]:
    """Letters with a mark Vietnamese does not use (Ě, Ü, Ō...): OCR misreading a Vietnamese diacritic."""
    return [c for c in text if c.isalpha() and any(m not in _VI_MARKS for m in unicodedata.normalize("NFD", c)[1:])]


# PP-OCR often writes the horn of ư/ơ as an apostrophe: "HU'O'NG" for "HƯƠNG", "ĐÚ'C" for "ĐỨC".
_HORN = re.compile("([UuOo][̀-̣̉]*)['’`ʼ]")


def normalize(text: str) -> str:
    """NFC (OCR may return a letter and its diacritics as separate code points), horns restored."""
    text = unicodedata.normalize("NFD", text.replace("Ð", "Đ"))
    text = _HORN.sub(lambda m: m.group(1)[0] + "̛" + m.group(1)[1:], text)
    return unicodedata.normalize("NFC", text).strip()


# Card designs: "2024" = thẻ căn cước (since 01/07/2024), "cccd_2021" = Căn cước công dân with chip (2021–06/2024,
# still valid until its expiry date). Same bilingual one-line labels, different wording and layout; the 2021 card
# also prints place of origin and place of residence on the front.
DESIGNS = ("2024", "cccd_2021")

# Vietnamese label and English sub-label (after "/"), in reading order; either one is enough to find the field.
# The English half is printed in small italics and comes back mangled ("Dota ofbirt", "Nationalty"), so it is
# matched loosely but case-sensitively (it is title case, values are capitals or digits).
_DOB_EN = r"D[a-z]{2,3}\s*o[a-z]?\s*b[a-z]*"
_EXPIRY = (vi_pattern("co gia tri den"), r"D[a-z]{2,3}\s*o[a-z]?\s*e[a-z]*")
_SEX = (vi_pattern("gioi tinh"), r"Se[a-z]")
_NATIONALITY = (vi_pattern("quoc tich"), r"Na[a-z]{4,}|N[a-z]{5,}ty")
LABEL_TEXTS: dict[str, dict[str, tuple[str, str]]] = {
    "2024": {
        "id_number": (vi_pattern("so dinh danh ca nhan"), r"No\b\.?"),
        "full_name": (vi_pattern("ho, chu dem va ten khai sinh") + r"|" + vi_pattern("ho, chu dem va ten"), r"Su[a-z]*\s*[,.]?\s*g[a-z]*\s*n[a-z]*"),
        "date_of_birth": (vi_pattern("ngay, thang, nam sinh"), _DOB_EN),
        "date_of_expiry": _EXPIRY,
        "sex": _SEX,
        "nationality": _NATIONALITY,
    },
    "cccd_2021": {
        # "Số" alone is two letters: only taken right before "/ No" (OCR: "Sô/No.:", "S6/No.3", "SolNo.:", "S/No.:").
        "id_number": (r"(?<![^\W\d_])S[^\W_]?(?=\s*[/|lI1]?\s*N[oO0])", r"No\b\.?"),
        "full_name": (vi_pattern("ho va ten"), r"F[a-z]{2,3}\s*n[a-z]*"),
        "date_of_birth": (vi_pattern("ngay sinh"), _DOB_EN),
        "date_of_expiry": _EXPIRY,
        "sex": _SEX,
        "nationality": _NATIONALITY,
        "place_of_origin": (vi_pattern("que quan"), r"P[a-z]{3,4}\s*o[a-z]?\s*or[a-z]*"),
        "place_of_residence": (vi_pattern("noi thuong tru"), r"P[a-z]{3,4}\s*o[a-z]?\s*re[a-z]*"),
    },
}
# "No." alone is too short to trust anywhere on the card: it only counts right after a separator or at a line start.
_EN_GUARD = {"id_number": r"(?:(?<=[/|])|^)\s*"}
# Between the two halves: "/", which OCR also reads as "I", "l", "1" or "|", or both ("tich/ I Nationality");
# with no "/" the English half must follow.
_SEP = r"(?:\s*/\s*(?:[|lI1]\s+)?(?-i:{en})?|\s*[|lI1]\s*(?-i:{en}))?"

VI_LABELS = {d: {k: re.compile(rf"(?:{vi})", re.IGNORECASE) for k, (vi, _) in t.items()} for d, t in LABEL_TEXTS.items()}
# The whole printed label: "Vietnamese / English:" or either half alone, with the trailing colon.
LABELS = {
    d: {
        k: re.compile(
            rf"(?:{vi})" + _SEP.format(en=en) + rf"\s*[:;.]?|{_EN_GUARD.get(k, '')}(?<![^\W\d_])(?:[|lI1]\s+)?(?-i:{en})\s*[:;.]?",
            re.IGNORECASE | re.MULTILINE,
        )
        for k, (vi, en) in t.items()
    }
    for d, t in LABEL_TEXTS.items()
}
ENGLISH_SUBLABELS = re.compile(
    r"[/|]\s*(?:" + "|".join(en for t in LABEL_TEXTS.values() for _, en in t.values()) + r")\s*[:;.]?"
    r"|\b(?i:(?:Citizen\s*)?Identity\s*Card|SOCIALIST\s*REPUBLIC\s*OF\s*VIET\s*NAM|Independence\s*-?\s*Freedom\s*-?\s*Happiness)\b",
)

TITLE_RE = re.compile(vi_pattern("can cuoc") + r"|Identity\s*Card", re.IGNORECASE)
# Căn cước công dân title: the 2021 chip card (the 2016 barcode card has the same title, untested).
CCCD_TITLE_RE = re.compile(vi_pattern("can cuoc cong dan") + r"|Citizen\s*Identity", re.IGNORECASE)

DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{4})(?!\d)")
NO_EXPIRY_RE = re.compile(vi_pattern("khong thoi han"), re.IGNORECASE)
# 12 digits, with the letters OCR reads in place of digits; spaces inside are allowed.
ID_NUMBER_RE = re.compile(r"(?<![0-9A-Za-z])(?:[0-9OoDQIlLSBZ]\s?){11}[0-9OoDQIlLSBZ](?![0-9A-Za-z])")
TO_DIGIT = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "I": "1", "l": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})

SEXES = {"nam": "Nam", "nu": "Nữ"}
NATIONALITIES = ["Việt Nam"]

# First 3 digits of the personal identification number: province/city where the birth was registered
# (Thông tư 07/2016/TT-BCA; the 63 provinces before the 2025 merger, codes unchanged).
PROVINCE_CODES = {
    "001": "Hà Nội", "002": "Hà Giang", "004": "Cao Bằng", "006": "Bắc Kạn", "008": "Tuyên Quang",
    "010": "Lào Cai", "011": "Điện Biên", "012": "Lai Châu", "014": "Sơn La", "015": "Yên Bái",
    "017": "Hòa Bình", "019": "Thái Nguyên", "020": "Lạng Sơn", "022": "Quảng Ninh", "024": "Bắc Giang",
    "025": "Phú Thọ", "026": "Vĩnh Phúc", "027": "Bắc Ninh", "030": "Hải Dương", "031": "Hải Phòng",
    "033": "Hưng Yên", "034": "Thái Bình", "035": "Hà Nam", "036": "Nam Định", "037": "Ninh Bình",
    "038": "Thanh Hóa", "040": "Nghệ An", "042": "Hà Tĩnh", "044": "Quảng Bình", "045": "Quảng Trị",
    "046": "Thừa Thiên Huế", "048": "Đà Nẵng", "049": "Quảng Nam", "051": "Quảng Ngãi", "052": "Bình Định",
    "054": "Phú Yên", "056": "Khánh Hòa", "058": "Ninh Thuận", "060": "Bình Thuận", "062": "Kon Tum",
    "064": "Gia Lai", "066": "Đắk Lắk", "067": "Đắk Nông", "068": "Lâm Đồng", "070": "Bình Phước",
    "072": "Tây Ninh", "074": "Bình Dương", "075": "Đồng Nai", "077": "Bà Rịa - Vũng Tàu", "079": "TP. Hồ Chí Minh",
    "080": "Long An", "082": "Tiền Giang", "083": "Bến Tre", "084": "Trà Vinh", "086": "Vĩnh Long",
    "087": "Đồng Tháp", "089": "An Giang", "091": "Kiên Giang", "092": "Cần Thơ", "093": "Hậu Giang",
    "094": "Sóc Trăng", "095": "Bạc Liêu", "096": "Cà Mau",
}
# 4th digit: century of birth and sex (0/1 = 1900s male/female, 2/3 = 2000s, 4/5 = 2100s...).
CENTURY_SEX_DIGIT = {(1900, "Nam"): "0", (1900, "Nữ"): "1", (2000, "Nam"): "2", (2000, "Nữ"): "3", (2100, "Nam"): "4", (2100, "Nữ"): "5"}
# The card must be renewed at these ages: it expires on that birthday (Luật Căn cước 2023, Điều 21;
# Luật Căn cước công dân 2014, Điều 21 for the 2021 card). Past the last one it has no expiry.
RENEWAL_AGES = {"2024": (14, 25, 40, 60), "cccd_2021": (25, 40, 60)}
