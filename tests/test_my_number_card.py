"""My Number card (個人番号カード) parser tests on hand-written boxes laid out like the front of the card. No Paddle needed."""

import datetime as dt

from app.card_core.field import Field
from app.my_number_card import parse_my_number_card
from app.my_number_card.parser import cross_check
from app.ocr.types import OcrBox


def line(text: str, x: float, y: float, score: float = 0.98, w: float = 300, h: float = 40) -> OcrBox:
    return OcrBox(text=text, score=score, box=(x, y, x + w, y + h))


def card(*, expiry="2035年 3月31日", marker="まで有効", issuer="名古屋市長", address="愛知県名古屋市中区三の丸三丁目1番1号"):
    return [
        line("個人番号カード", 40, 30, w=360),
        line("氏名", 40, 120, w=70),
        line("番号 花子", 130, 120, w=260),
        line("住所", 40, 200, w=70),
        line(address, 130, 200, w=900),
        line("平成元年 3月31日生", 40, 290, w=360),
        line("性別 女", 430, 290, w=140),
        line(expiry, 40, 380, w=330),
        line(marker, 380, 380, w=150),
        line(issuer, 40, 560, w=220),
    ]


def values(result: dict) -> dict:
    return {k: v["value"] for k, v in result["fields"].items()}


def test_reads_issuer_and_expiry():
    r = parse_my_number_card(card())
    assert r["document_type"] == "my_number_card"
    assert values(r) == {"issuer": "名古屋市長", "expiry_date": "2035-03-31"}
    assert not any(f["needs_review"] for f in r["fields"].values())
    assert r["quality"]["level"] == "ok"
    assert r["warnings"] == []


def test_fullwidth_digits_and_kana_city():
    r = parse_my_number_card(card(expiry="２０３２年１２月　１日", issuer="さいたま市長"))
    assert values(r) == {"issuer": "さいたま市長", "expiry_date": "2032-12-01"}


def test_address_with_ward_head_like_text_is_not_issuer():
    # "区長田町" in an address must not be read as the issuer "…区長".
    r = parse_my_number_card(card(address="東京都千代田区長田町1丁目", issuer="千代田区長"))
    assert values(r)["issuer"] == "千代田区長"
    r = parse_my_number_card(card(address="東京都千代田区長田町1丁目", issuer=""))
    assert values(r)["issuer"] is None


def test_marker_missing_takes_latest_date_and_flags_it():
    r = parse_my_number_card(card(marker=""))
    f = r["fields"]["expiry_date"]
    assert f["value"] == "2035-03-31"  # not the birth date
    assert f["needs_review"] and f["notes"]


def test_marker_in_same_box_as_date():
    r = parse_my_number_card(card(expiry="2030年 1月 5日まで有効", marker=""))
    assert values(r)["expiry_date"] == "2030-01-05"
    assert not r["fields"]["expiry_date"]["needs_review"]


def test_low_confidence_needs_review():
    boxes = card()
    boxes[-1] = line("名古屋市長", 40, 560, score=0.6, w=220)
    assert parse_my_number_card(boxes)["fields"]["issuer"]["needs_review"]


def test_not_a_my_number_card_warns():
    r = parse_my_number_card([line("在留カード", 40, 30)])
    assert values(r) == {"issuer": None, "expiry_date": None}
    assert any("個人番号カード" in w for w in r["warnings"])


def test_zone_mode_falls_back_to_pattern_reading():
    r = parse_my_number_card(card(), (1100, 700), True, "zone")
    assert values(r) == {"issuer": "名古屋市長", "expiry_date": "2035-03-31"}
    assert any("template" in w for w in r["warnings"])


def test_cross_check_expired_and_too_far():
    expired = {"expiry_date": Field(value="2020-01-01", needs_review=False)}
    assert any("hết hạn" in w for w in cross_check(expired, dt.date(2026, 10, 28)))
    far = {"expiry_date": Field(value="2050-01-01", needs_review=False)}
    assert cross_check(far, dt.date(2026, 10, 28)) and far["expiry_date"].needs_review
