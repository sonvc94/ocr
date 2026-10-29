"""Special permanent resident certificate, driving history certificate, 住基カード, 住民票の写し, pension handbook:
hand-written boxes with made-up data (no Paddle needed), detection, and My Number masking."""

import datetime as dt
import json
from pathlib import Path

import numpy as np

from app import pipeline
from app.card_core.redact import redact_my_number
from app.detect import detect_document
from app.driver_license import parse_driving_history
from app.juki_card import parse_juki_card
from app.juki_card.parser import cross_check as juki_check
from app.card_core.field import Field
from app.ocr.types import OcrBox
from app.pension import parse_pension
from app.resident_record import parse_resident_record
from app.special_permanent import parse_special_permanent


def line(text: str, x: float, y: float, score: float = 0.98, w: float = 300, h: float = 40) -> OcrBox:
    return OcrBox(text=text, score=score, box=(x, y, x + w, y + h))


def values(result: dict) -> dict:
    return {k: v["value"] for k, v in result["fields"].items()}


# --- 特別永住者証明書 ------------------------------------------------------------------------------------

def special_permanent(number="番号 AB12345678CD"):
    return [
        line("特別永住者証明書", 500, 20, w=420), line("SPECIAL PERMANENT RESIDENT CERTIFICATE", 450, 70, w=600),
        line(number, 1100, 20, w=420),
        line("氏名", 40, 140, w=70), line("KIM MINJUN", 130, 140, w=400),
        line("生年月日", 40, 220, w=140), line("1990年01月02日", 200, 220, w=300), line("国籍・地域 韓国", 700, 220, w=300),
        line("住居地", 40, 300, w=100), line("大阪府大阪市生野区桃谷1丁目1番1号", 160, 300, w=700),
        line("有効期間の満了日", 40, 860, w=300), line("2031年01月02日", 360, 860, w=300),
    ]


def test_special_permanent_reads_number_and_expiry():
    r = parse_special_permanent(special_permanent())
    assert r["document_type"] == "special_permanent_resident_certificate"
    assert values(r) == {"certificate_number": "AB12345678CD", "expiry_date": "2031-01-02"}


def test_special_permanent_fixes_letters_read_as_digits():
    f = parse_special_permanent(special_permanent("番号 A8I2345678C0"))["fields"]["certificate_number"]
    assert f["value"] == "AB12345678CO" and f["needs_review"]  # 2 letters + 8 digits + 2 letters


def test_detects_special_permanent_not_residence_card():
    d = detect_document(special_permanent())
    assert d.document == "jp_special_permanent" and d.confident


# --- 運転経歴証明書 ---------------------------------------------------------------------------------------

def driving_history():
    return [
        line("運転経歴証明書", 40, 20, w=400),
        line("氏名", 40, 100, w=70), line("日本 一郎", 130, 100, w=260), line("昭和20年 1月 1日生", 700, 100, w=330),
        line("住所", 40, 180, w=70), line("東京都千代田区霞が関2丁目1番1号", 130, 180, w=700),
        line("交付", 40, 260, w=70), line("令和05年04月01日 54321", 130, 260, w=420),
        line("免許の条件等", 40, 340, w=200), line("番号", 40, 640, w=70), line("第 301234567890 号", 130, 640, w=420),
        line("東京都公安委員会", 1000, 900, w=330),
    ]


def test_driving_history_reads_number_and_issue_date():
    r = parse_driving_history(driving_history())
    assert r["document_type"] == "driving_history_certificate"
    assert values(r) == {"license_number": "301234567890", "issue_date": "2023-04-01"}
    assert not any("運転経歴証明書 —" in w for w in r["warnings"])


def test_detects_driving_history_not_driver_license():
    d = detect_document(driving_history())
    assert d.document == "jp_driving_history" and d.confident


# --- 住民基本台帳カード -----------------------------------------------------------------------------------

def juki_card(expiry="有効期限 平成37年 3月31日"):
    return [
        line("住民基本台帳カード", 40, 20, w=450),
        line("氏名", 40, 120, w=70), line("総務 花子", 130, 120, w=260),
        line("住所", 40, 200, w=70), line("東京都千代田区霞が関2丁目1番2号", 130, 200, w=700),
        line("昭和50年 5月 5日生", 40, 280, w=330), line(expiry, 40, 360, w=500),
        line("千代田区長", 900, 900, w=220),
    ]


def test_juki_card_reads_issuer_and_expiry_and_warns_expired():
    r = parse_juki_card(juki_card())
    assert r["document_type"] == "juki_card"
    assert values(r) == {"issuer": "千代田区長", "expiry_date": "2025-03-31"}
    assert any("hết hạn" in w for w in r["warnings"])


def test_juki_card_expiry_after_last_possible_is_flagged():
    fields = {"expiry_date": Field(value="2031-01-01")}
    juki_check(fields, today=dt.date(2026, 10, 29))
    assert fields["expiry_date"].needs_review


def test_detects_juki_card():
    assert detect_document(juki_card()).document == "jp_juki_card"


# --- 住民票の写し -----------------------------------------------------------------------------------------

def resident_record(my_number="1234 5678 9012"):
    return [
        line("住民票", 600, 20, w=200),
        line("住所", 40, 120, w=70), line("東京都千代田区霞が関2丁目1番2号", 140, 120, w=700),
        line("世帯主", 900, 120, w=100), line("総務 太郎", 1020, 120, w=200),
        line("氏名", 40, 220, w=70), line("総務 太郎", 140, 220, w=260), line("続柄 世帯主", 900, 220, w=200),
        line("生年月日", 40, 300, w=140), line("昭和50年 5月 5日", 200, 300, w=300),
        line("住民となった日", 40, 380, w=240), line("平成20年 4月 1日", 300, 380, w=300),
        line("個人番号", 40, 460, w=140), line(my_number, 200, 460, w=300),
        line("この写しは、住民票の原本と相違ないことを証明する。", 40, 900, w=900),
        line("令和 8年 9月 1日", 40, 960, w=300), line("東京都千代田区長 千代田 一郎", 600, 960, w=500),
    ]


def test_resident_record_reads_issuer_date_and_address():
    r = parse_resident_record(resident_record())
    assert r["document_type"] == "resident_record"
    assert values(r) == {"issuer": "東京都千代田区長", "certified_date": "2026-09-01", "address": "東京都千代田区霞が関2丁目1番2号"}


def test_detects_resident_record():
    d = detect_document(resident_record())
    assert d.document == "jp_resident_record" and d.confident


def test_my_number_masked_next_to_label_only():
    boxes = [line("個人番号", 40, 460, w=140), line("1234 5678 9012", 200, 460, w=300), line("第 301234567890 号", 40, 640)]
    out, changed = redact_my_number(boxes)
    assert [b.text for b in out] == ["個人番号", "**** **** ****", "第 301234567890 号"] and len(changed) == 1


def test_my_number_masked_everywhere_on_resident_record(monkeypatch):
    """Through the pipeline: the number is gone from the lines, full_text and the returned image."""
    boxes = resident_record() + [line("123456789012", 40, 700)]  # separate cell, away from the label

    def fake_ocr(img, engine, lang):
        return list(boxes), img, 0.0, "stub", None

    monkeypatch.setattr(pipeline, "_ocr", fake_ocr)
    img = np.full((1100, 1300, 3), 255, np.uint8)
    result, out = pipeline.extract(img, (1300, 1100), document="jp_resident_record")
    texts = " ".join(l["text"] for l in result["ocr"]["lines"]) + result["full_text"]
    assert "5678" not in texts and "123456789012" not in texts and "****" in texts
    assert out[470, 300].tolist() == [0, 0, 0] and img[470, 300].tolist() == [255, 255, 255]  # blacked out on a copy
    assert any("My Number" in w for w in result["warnings"])
    assert not result["ocr"]["card_cropped"]


# --- 年金手帳 / 基礎年金番号通知書 ------------------------------------------------------------------------

def pension_book(number="1234-567890"):
    return [
        line("国民年金手帳", 40, 20, w=300),
        line("基礎年金番号", 40, 120, w=220), line(number, 300, 120, w=300),
        line("氏名", 40, 200, w=70), line("年金 花子", 130, 200, w=260),
        line("生年月日", 40, 280, w=140), line("昭和55年 6月 6日", 200, 280, w=300),
        line("交付年月日", 40, 360, w=180), line("平成12年 4月 1日", 240, 360, w=300),
        line("日本年金機構", 40, 900, w=260),
    ]


def test_pension_book_reads_number_and_issue_date():
    r = parse_pension(pension_book())
    assert r["document_type"] == "pension_book"
    assert values(r) == {"basic_pension_number": "1234-567890", "issue_date": "2000-04-01"}


def test_pension_number_fixes_ocr_letters():
    f = parse_pension(pension_book("I234-S67890"))["fields"]["basic_pension_number"]
    assert f["value"] == "1234-567890" and f["needs_review"]


def test_detects_pension_book():
    assert detect_document(pension_book()).document == "jp_pension_book"


def test_pages_are_not_cropped():
    assert not pipeline.DOCUMENTS["jp_resident_record"][2] and not pipeline.DOCUMENTS["jp_pension_book"][2]


# --- official specimens (見本), real PP-OCRv5 output (tests/fixtures/official_*_ocr.json) ------------------

FIXTURES = Path(__file__).parent / "fixtures"


def official(name: str, parse) -> dict:
    d = json.loads((FIXTURES / f"official_{name}_ocr.json").read_text())
    return parse([OcrBox(l["text"], l["score"], tuple(l["box"])) for l in d["lines"]], tuple(d["image_size"]), d["cropped"])


def test_official_special_permanent_all_designs():
    for name, expiry in (("special_permanent_resident", "2026-04-01"), ("special_permanent_resident_2026", "2036-04-01"),
                         ("special_permanent_resident_specified_2026", "2037-03-31")):
        assert values(official(name, parse_special_permanent)) == {"certificate_number": "AB12345678CD", "expiry_date": expiry}


def test_official_driving_history():
    r = official("driving_history", parse_driving_history)
    assert values(r) == {"license_number": "123456789000", "issue_date": "2012-04-01"}
    # 298px Aichi specimen: 交付 read as 交计, the date is still the only one that is neither birth nor expiry
    r = official("driving_history_aichi", parse_driving_history)
    assert values(r) == {"license_number": "541199999980", "issue_date": "2015-01-01"}  # 54 = 愛知


def test_official_juki_cards():
    # the card prints the municipality alone (横浜市), not ○○市長; the 総務省 schematic uses △△市
    assert values(official("juki_card", parse_juki_card)) == {"issuer": "△△市", "expiry_date": "2013-08-31"}
    assert values(official("juki_card_yokohama", parse_juki_card)) == {"issuer": "横浜市", "expiry_date": "2015-01-25"}


def test_official_resident_record():
    # Kobe standard layout: the address sits on the row above its 住所 label; 住所(を)定めた年月日 is not the address;
    # the certification date is a placeholder (令和●年●月日), so none (not the 届出日 printed above).
    r = official("resident_record", parse_resident_record)
    assert values(r) == {"issuer": "兵庫県神戸市中央区長", "certified_date": None, "address": "兵庫県神戸市中央区加納町6丁目5番1号"}


def test_official_pension_specimens_have_placeholders_only():
    # 基礎年金番号通知書 shows XXXX-XXXXXX / 令和X年X月X日; the 年金手帳 page is a blank form: nothing to read, nothing invented.
    for name in ("pension_notice", "pension_book"):
        assert values(official(name, parse_pension)) == {"basic_pension_number": None, "issue_date": None}
