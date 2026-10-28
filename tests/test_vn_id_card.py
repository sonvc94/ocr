"""Vietnamese identity card parser tests (thẻ căn cước 2024, chip CCCD 2021): real OCR output of the specimen-based
samples (tests/fixtures/vn_*.json, read with PP-OCRv6_medium_rec) and hand-written boxes. No Paddle needed.

tests/fixtures/vn_real2021_*.json are OCR of photos of a real person's card: git-ignored, and the tests using them
check structure and consistency only (no personal data in this file); skipped when absent (make them with
scripts/make_vn_fixtures.py from logs/images/)."""

import json
from pathlib import Path

import pytest

from app.card_core.field import Field
from app.ocr.types import OcrBox
from app.vn_id_card import parse_vn_id_card
from app.vn_id_card.checks import cross_check
from app.vn_id_card.patterns import LABELS, normalize

FIXTURES = Path(__file__).parent / "fixtures"


def parse_fixture(name: str, mode: str = "label") -> dict:
    d = json.loads((FIXTURES / name).read_text())
    boxes = [OcrBox(l["text"], l["score"], tuple(l["box"])) for l in d["lines"]]
    return parse_vn_id_card(boxes, tuple(d["image_size"]), d["cropped"], mode)


def values(result: dict) -> dict:
    return {k: v["value"] for k, v in result["fields"].items()}


def line(text: str, x: float, y: float, score: float = 0.98, w: float = 300, h: float = 40) -> OcrBox:
    return OcrBox(text=text, score=score, box=(x, y, x + w, y + h))


CARD = [
    line("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", 454, 46, w=766),
    line("CĂN CƯỚC", 611, 238, w=446, h=86),
    line("Identity Card", 639, 355, w=216),
    line("Số định danh cá nhân / No.:", 471, 431, w=495),
    line("001195012345", 975, 435, w=340),
    line("Họ, chữ đệm và tên khai sinh / Surname, given names:", 476, 586, w=934),
    line("NGUYỄN THỊ THU HƯƠNG", 480, 665, w=660, h=50),
    line("Ngày, tháng, năm sinh / Date of birth:", 475, 767, w=634),
    line("12/04/1995", 1115, 770, w=210),
    line("Có giá trị đến / Date of expiry", 53, 880, w=376),
    line("Giới tính / Sex:", 475, 882, w=258),
    line("Nữ", 745, 885, w=60),
    line("Quốc tịch / Nationality:", 877, 884, w=366),
    line("Việt Nam", 1265, 885, w=180),
    line("12/04/2035", 60, 945, w=190),
]
EXPECTED = {
    "id_number": "001195012345",
    "full_name": "NGUYỄN THỊ THU HƯƠNG",
    "date_of_birth": "1995-04-12",
    "sex": "Nữ",
    "nationality": "Việt Nam",
    "date_of_expiry": "2035-04-12",
}


def test_clean_card_all_fields_no_review():
    r = parse_vn_id_card(CARD)
    assert values(r) == EXPECTED
    assert not any(f["needs_review"] for f in r["fields"].values())
    assert r["warnings"] == []
    assert r["document_type"] == "vn_id_card" and r["card_design"] == "2024"


def test_expiry_under_photo_is_not_the_birth_date():
    # The expiry label shares its row with sex and nationality; its date is on the row below.
    r = parse_vn_id_card(CARD)
    assert r["fields"]["date_of_expiry"]["value"] == "2035-04-12"
    assert r["fields"]["date_of_birth"]["value"] == "1995-04-12"


def test_horn_read_as_apostrophe_is_restored():
    assert normalize("NGUYÊN THI THU HU'O'NG") == "NGUYÊN THI THU HƯƠNG"
    assert normalize("TRÀN ĐÚ'C ANH") == "TRÀN ĐỨC ANH"


def test_labels_tolerate_ocr_damage():
    # real PP-OCR reads of the printed labels
    for key, text in [
        ("id_number", "Só đjnh danh cá nhán/No"),
        ("full_name", "Ho, chùr dęm và tén khai sinh/Suname given nanes"),
        ("date_of_birth", "Ngay, tháng, năm sinh/Data ofbir12/04/1995"),
        ("sex", "Giói tinh/Sex:"),
        ("nationality", "Quóc tich/NationaltyViêt Nam"),
    ]:
        assert LABELS["2024"][key].search(text), (key, text)
    assert LABELS["2024"]["nationality"].search("Quóc tich/NationaltyViêt Nam").group(0) == "Quóc tich/Nationalty"


def test_synthetic_scan_label_mode():
    r = parse_fixture("vn_synthetic_1_ocr.json")
    assert values(r) == {
        "id_number": "079203004567",
        "full_name": "TRÀN ĐỨC ANH",  # OCR read Ầ as À: a real misread, kept as read
        "date_of_birth": "2003-11-05",
        "sex": "Nam",
        "nationality": "Việt Nam",
        "date_of_expiry": "2028-11-05",
    }
    # the tiny expiry label is unreadable: the date is found by elimination and flagged
    assert r["fields"]["date_of_expiry"]["needs_review"]
    assert r["warnings"] == []


def test_zone_and_hybrid_on_photo():
    for mode in ("zone", "hybrid"):
        r = parse_fixture("vn_synthetic_1_photo_ocr.json", mode)
        assert r["layout"]["registration"]["method"] == "anchors"
        assert r["layout"]["registration"]["anchors_used"] >= 5
        assert set(r["layout"]["zones_px"]) == set(EXPECTED)
        assert values(r)["id_number"] == "079203004567"
        assert values(r)["nationality"] == "Việt Nam"  # the OCR line also holds the label: split at its end
        assert values(r)["date_of_expiry"] == "2028-11-05"
    hybrid = parse_fixture("vn_synthetic_1_photo_ocr.json", "hybrid")
    # the position on the card confirms the expiry date found by elimination
    assert hybrid["fields"]["date_of_expiry"]["source"] == "label+zone"
    assert not hybrid["fields"]["date_of_expiry"]["needs_review"]


def test_specimen_without_values():
    r = parse_fixture("vn_can_cuoc_2024_specimen_ocr.json", "hybrid")
    assert all(v is None for v in values(r).values())
    assert r["layout"]["registration"] is not None
    assert not any("CĂN CƯỚC" in w for w in r["warnings"])


def fields(**vals) -> dict[str, Field]:
    out = {k: Field(value=None, needs_review=False) for k in EXPECTED}
    for k, v in vals.items():
        out[k].value = v
    return out


def test_cross_check_consistent():
    f = fields(id_number="001195012345", date_of_birth="1995-04-12", sex="Nữ", date_of_expiry="2035-04-12")
    assert cross_check(f, "2024") == []


def test_cross_check_id_number_rules():
    f = fields(id_number="999095012345", date_of_birth="1996-04-12", sex="Nữ")
    w = cross_check(f, "2024")
    assert any("mã tỉnh" in x for x in w)
    assert any("Số thứ 4" in x for x in w)  # 0 = male born 1900s
    assert any("năm sinh 1996" in x for x in w)
    assert f["id_number"].needs_review and f["sex"].needs_review and f["date_of_birth"].needs_review


def test_cross_check_expiry_on_renewal_birthday():
    ok = fields(date_of_birth="2003-11-05", date_of_expiry="2028-11-05")  # 25th birthday
    assert cross_check(ok, "2024") == []
    bad = fields(date_of_birth="2003-11-05", date_of_expiry="2030-11-05")
    assert any("sinh nhật tuổi" in x for x in cross_check(bad, "2024"))
    assert bad["date_of_expiry"].needs_review
    assert cross_check(fields(date_of_birth="1960-01-01", date_of_expiry="Không thời hạn"), "2024") == []


# Chip Căn cước công dân (2021 design), made-up person: card px 1600×1009, positions from data/templates.json "cccd_2021"
CARD_2021 = [
    line("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", 455, 55, w=760),
    line("SOCIALIST REPUBLIC OF VIET NAM", 570, 150, w=530, h=35),
    line("CĂN CƯỚC CÔNG DÂN", 455, 232, w=770, h=78),
    line("Citizen Identity Card", 462, 352, w=335),
    line("Số / No.:", 462, 438, w=150),
    line("079090001234", 640, 410, w=520, h=70),
    line("Họ và tên / Full name:", 467, 510, w=365),
    line("TRẦN VĂN BÌNH", 470, 557, w=450, h=60),
    line("Ngày sinh / Date of birth:", 467, 627, w=420),
    line("15/03/1990", 935, 625, w=250, h=45),
    line("Giới tính / Sex:", 472, 700, w=260),
    line("Nam", 760, 690, w=90, h=45),
    line("Quốc tịch / Nationality:", 895, 695, w=385),
    line("Việt Nam", 1305, 680, w=220, h=45),
    line("Quê quán / Place of origin:", 472, 768, w=445),
    line("Hòa Phú, Hòa Vang, Đà Nẵng", 480, 810, w=600, h=48),
    line("Có giá trị đến:", 50, 902, w=210),
    line("15/03/2030", 262, 905, w=200),
    line("Nơi thường trú / Place of residence:", 472, 872, w=620),
    line("12 Lê Lợi", 1100, 870, w=200),
    line("Bến Nghé, Quận 1, TP. Hồ Chí Minh", 480, 935, w=700, h=50),
    line("Date of expiry", 50, 940, w=190, h=35),
]
EXPECTED_2021 = {
    "id_number": "079090001234",
    "full_name": "TRẦN VĂN BÌNH",
    "date_of_birth": "1990-03-15",
    "sex": "Nam",
    "nationality": "Việt Nam",
    "date_of_expiry": "2030-03-15",
    "place_of_origin": "Hòa Phú, Hòa Vang, Đà Nẵng",
    "place_of_residence": "12 Lê Lợi Bến Nghé, Quận 1, TP. Hồ Chí Minh",
}


def test_cccd_2021_all_modes():
    for mode in ("label", "zone", "hybrid"):
        r = parse_vn_id_card(CARD_2021, (1600, 1009), True, mode)
        assert r["card_design"] == "cccd_2021"
        assert values(r) == EXPECTED_2021, mode
        assert r["warnings"] == []
        if mode == "hybrid":
            assert r["layout"]["registration"]["method"] == "anchors"
            assert all(f["source"] == "label+zone" and not f["needs_review"] for f in r["fields"].values())


def test_cccd_2021_labels_tolerate_ocr_damage():
    labels = LABELS["cccd_2021"]
    for key, text in [  # real PP-OCR reads
        ("id_number", "S6/No.3"),
        ("id_number", "SolNo.: 079090001234"),
        ("full_name", "Ho và tên I Full name:"),
        ("nationality", "Qudc tich / Netionality: Vit Nam"),
        ("place_of_residence", "Noi thurong trú I Place of residence: P424-L3"),
        ("date_of_expiry", "Có giá trj dén: 15/03/2030"),
    ]:
        assert labels[key].search(text), (key, text)
    # "/" also read as "I": the whole label is consumed, not left in the value
    assert labels["nationality"].search("Quoc tich/ I Nationality: Viêt Nam").group(0) == "Quoc tich/ I Nationality:"
    assert not labels["id_number"].search("Khánh Sơn, Nam Đàn")


def test_cccd_2021_expiry_before_english_label():
    # Vietnamese expiry label unreadable: its date is printed above "Date of expiry"
    boxes = [b if b.text != "Có giá trị đến:" else line("Co gia ey dèn:", 50, 902, w=210) for b in CARD_2021]
    r = parse_vn_id_card(boxes)
    assert values(r)["date_of_expiry"] == "2030-03-15"
    assert values(r)["place_of_residence"] == EXPECTED_2021["place_of_residence"]
    # same row as the start of the address
    boxes = [b for b in boxes if b.text != "12 Lê Lợi"] + [line("12 Lê Lợi", 480, 902, w=200)]
    assert values(parse_vn_id_card(boxes))["place_of_residence"].startswith("12 Lê Lợi")


def test_cccd_2021_renewal_ages():
    # expiring at 14 exists only on the 2024 card
    assert cross_check(fields(date_of_birth="2015-11-05", date_of_expiry="2029-11-05"), "2024") == []
    w = cross_check(fields(date_of_birth="2015-11-05", date_of_expiry="2029-11-05"), "cccd_2021")
    assert any("25/40/60" in x for x in w)


def test_name_with_non_vietnamese_mark_is_flagged():
    # PP-OCR reads the circumflex + tilde of Ễ as a caron (Ě), with high confidence
    boxes = [b if b.text != "TRẦN VĂN BÌNH" else line("NGUYĚN VĂN BÌNH", 470, 557, w=450, h=60) for b in CARD_2021]
    f = parse_vn_id_card(boxes)["fields"]["full_name"]
    assert f["needs_review"] and "Ě" in f["notes"][0]


REAL_2021 = sorted(FIXTURES.glob("vn_real2021_*_ocr.json"))


@pytest.mark.skipif(not REAL_2021, reason="real-card fixtures are git-ignored (personal data)")
@pytest.mark.parametrize("path", REAL_2021, ids=[p.stem for p in REAL_2021])
def test_cccd_2021_real_photos_hybrid(path):
    r = parse_fixture(path.name, "hybrid")
    assert r["card_design"] == "cccd_2021"
    assert r["layout"]["registration"]["anchors_used"] >= 8
    assert all(f["value"] for f in r["fields"].values())
    assert r["fields"]["nationality"]["value"] == "Việt Nam"
    # ID number, birth date, sex and expiry all agree with each other (cross_check), so none was misread
    assert r["warnings"] == []
    for key in ("id_number", "date_of_birth", "date_of_expiry"):
        assert r["fields"][key]["source"] == "label+zone"
