"""Pattern-only Japanese documents (driver's license, passport, health insurance card) and the residence card
restricted to its card number: hand-written boxes with made-up data, and the OCR of official specimens. No Paddle needed."""

import datetime as dt
import json
from functools import partial
from pathlib import Path

from app.card_core.field import Field
from app.driver_license import parse_driver_license
from app.driver_license.parser import cross_check as license_check
from app.health_insurance import parse_health_insurance
from app.my_number_card import parse_my_number_card
from app.ocr.types import OcrBox
from app.passport import parse_passport
from app.passport.patterns import mrz_check_digit
from app.pipeline import DOCUMENTS


def line(text: str, x: float, y: float, score: float = 0.98, w: float = 300, h: float = 40) -> OcrBox:
    return OcrBox(text=text, score=score, box=(x, y, x + w, y + h))


def values(result: dict) -> dict:
    return {k: v["value"] for k, v in result["fields"].items()}


def review(result: dict) -> dict:
    return {k: v["needs_review"] for k, v in result["fields"].items()}


# --- driver's license ---------------------------------------------------------------------------------

def license_card(number="第 301234567890 号", issue_label="交付", issue="令和03年05月10日 12345"):
    return [
        line("氏名", 40, 60, w=70), line("日本 花子", 130, 60, w=260), line("昭和60年 1月 1日生", 700, 60, w=330),
        line("住所", 40, 160, w=70), line("東京都千代田区霞が関2丁目1番1号", 130, 160, w=700),
        line(issue_label, 40, 260, w=70), line(issue, 130, 260, w=420),
        line("2029年(令和11年)06月01日まで有効", 40, 360, w=600),
        line("番号", 40, 640, w=70), line(number, 130, 640, w=420), line("運転免許証", 650, 650, w=250),
        line("東京都公安委員会", 1000, 900, w=350),
    ]


def test_driver_license():
    r = parse_driver_license(license_card())
    assert r["document_type"] == "driver_license"
    assert values(r) == {"license_number": "301234567890", "issue_date": "2021-05-10"}
    assert not any(review(r).values())
    assert r["warnings"] == []


def test_driver_license_spaced_digits_and_lookalikes():
    r = parse_driver_license(license_card(number="第 30 12345678 9O 号"))
    assert values(r)["license_number"] == "301234567890"
    assert review(r)["license_number"]  # a letter was turned into a digit


def test_driver_license_unknown_commission_code():
    r = parse_driver_license(license_card(number="第 991234567890 号"))
    assert review(r)["license_number"] and r["warnings"]


def test_driver_license_issue_label_missing_guesses_middle_date():
    r = parse_driver_license(license_card(issue_label="", issue="令和03年05月10日 12345"))
    assert values(r)["issue_date"] == "2021-05-10"
    assert review(r)["issue_date"]


def test_driver_license_future_issue_date():
    fields = {"license_number": Field(value="301234567890"), "issue_date": Field(value="2030-01-01", needs_review=False)}
    assert license_check(fields, dt.date(2026, 10, 28)) and fields["issue_date"].needs_review


# --- passport -------------------------------------------------------------------------------------------

def mrz2(number="TR1234567", check=None):
    check = mrz_check_digit(number) if check is None else check
    return f"{number}{check}JPN9001011F3404012<<<<<<<<<<<<<<04"


def passport_page(printed="TR1234567", mrz_line=None):
    return [
        line("日本国 JAPAN", 40, 40, w=300), line("旅券 PASSPORT", 600, 40, w=300),
        line("旅券番号/Passport No.", 1000, 140, w=300, h=30), line(printed, 1000, 175, w=220),
        line("姓/Surname", 520, 240, w=200, h=30), line("NIHON", 520, 275, w=150),
        line("P<JPNNIHON<<HANAKO<<<<<<<<<<<<<<<<<<<<<<<<<", 40, 930, w=1500),
        line(mrz_line or mrz2(), 40, 1010, w=1500),
    ]


def test_passport_mrz_and_printed_agree():
    r = parse_passport(passport_page())
    assert values(r) == {"passport_number": "TR1234567"}
    assert not review(r)["passport_number"]


def test_passport_mrz_with_misread_fillers_and_spaces():
    r = parse_passport(passport_page(printed="", mrz_line="TR12345 672JPN9001011F3404012«««««««04"))
    assert values(r) == {"passport_number": "TR1234567"}


def test_passport_bad_check_digit_falls_back_to_printed():
    r = parse_passport(passport_page(mrz_line=mrz2("TR1234561", check=0)))
    f = r["fields"]["passport_number"]
    assert f["value"] == "TR1234567" and f["needs_review"]


def test_passport_mrz_wins_over_misread_printed():
    r = parse_passport(passport_page(printed="TR1234561"))
    f = r["fields"]["passport_number"]
    assert f["value"] == "TR1234567" and f["needs_review"]  # the two disagree: noted


def test_passport_not_japanese_warns():
    r = parse_passport([line("PASSPORT", 0, 0), line("C01234567", 0, 60)])
    assert any("JAPAN" in w for w in r["warnings"])


# --- health insurance -----------------------------------------------------------------------------------

def health_card(title=("健康保険", "被保険者証"), issue=("令和 5年 4月 1日交付",), insurer="全国健康保険協会 東京支部 印"):
    return [
        line(title[0], 40, 40, w=200), line(title[1], 260, 40, w=220), line("本人(被保険者)", 500, 40, w=250),
        *[line(t, 1000, 40, w=400) for t in issue],
        line("記号 1234 番号 56", 40, 140, w=400),
        line("氏名", 40, 240, w=70), line("保険 花子", 130, 240, w=250),
        line("生年月日 昭和60年 1月 1日", 40, 340, w=500),
        line("資格取得年月日 令和 5年 4月 1日", 40, 440, w=600),
        line("保険者番号", 40, 700, w=200), line("01130012", 260, 700, w=200),
        line("保険者名称", 40, 800, w=200), line(insurer, 260, 800, w=600),
    ]


def test_health_insurance_kyokai_card():
    r = parse_health_insurance(health_card())
    assert r["document_type"] == "health_insurance_card"
    assert values(r) == {"card_type": "健康保険被保険者証", "insurer_name": "全国健康保険協会 東京支部", "issue_date": "2023-04-01"}
    assert not any(review(r).values())


def test_health_insurance_national_card_labels_and_dot_dates():
    boxes = [
        line("国民健康保険被保険者証", 40, 40, w=500),
        line("交付年月日 R5. 4. 1", 40, 140, w=400),
        line("世帯主氏名 国保 太郎", 40, 240, w=400),
        line("保険者番号 131016", 40, 700, w=400),
        line("交付者名", 40, 800, w=150), line("千代田区", 210, 800, w=200),
    ]
    r = parse_health_insurance(boxes)
    assert values(r) == {"card_type": "国民健康保険被保険者証", "insurer_name": "千代田区", "issue_date": "2023-04-01"}


def test_health_insurance_certificate_and_missing_scheme():
    assert values(parse_health_insurance(health_card(title=("健康保険", "資格確認書"))))["card_type"] == "健康保険資格確認書"
    r = parse_health_insurance(health_card(title=("", "被保険者証")))
    assert values(r)["card_type"] == "被保険者証" and review(r)["card_type"]


def test_health_insurance_not_a_card_warns():
    r = parse_health_insurance([line("運転免許証", 0, 0)])
    assert values(r) == {"card_type": None, "insurer_name": None, "issue_date": None}
    assert r["warnings"]


# --- registry -------------------------------------------------------------------------------------------

def test_residence_card_returns_card_number_only():
    parse, lang, crop = DOCUMENTS["jp_residence"]
    boxes = [
        line("在留カード", 600, 40), line("番号 AB12345678CD", 1100, 60, w=400),
        line("氏名 NGUYEN VAN AN", 40, 140, w=600), line("生年月日 1990年01月01日 性別 男 M.", 40, 260, w=900),
    ]
    r = parse(boxes)
    assert values(r) == {"card_number": "AB12345678CD"}
    assert isinstance(parse, partial) and lang == "ja" and crop


def test_passport_is_not_cropped():
    assert DOCUMENTS["jp_passport"][2] is False


# --- official specimens (見本) ---------------------------------------------------------------------------
# Real PP-OCRv5 output of the specimen images in samples/official/ (sources in samples/official/SOURCES.md),
# saved from the API (samples/results/official_*). Fake data printed by the issuing authorities.

FIXTURES = Path(__file__).parent / "fixtures"


def official(name: str, parse) -> dict:
    d = json.loads((FIXTURES / f"official_{name}_ocr.json").read_text())
    return parse([OcrBox(l["text"], l["score"], tuple(l["box"])) for l in d["lines"]], tuple(d["image_size"]), d["cropped"])


def test_official_passports():
    for name, number in (("passport_2025", "ZZ1000001"), ("passport_2020", "XS1234567")):
        r = official(name, parse_passport)
        assert values(r) == {"passport_number": number}
        assert not review(r)["passport_number"]  # MRZ check digit agrees with the printed number


def test_official_health_insurance_certificate():
    # Title on 2 lines with 有効期限 between them in the text; 交付者名 (municipal 国保).
    r = official("health_insurance_shikaku_kakuninsho", parse_health_insurance)
    assert values(r) == {"card_type": "国民健康保険資格確認書", "insurer_name": "名古屋市", "issue_date": "2026-08-01"}
    assert not any(review(r).values())


def test_official_my_number_card():
    # OCR reads まで有效 (simplified 效); the issuer □□市長 is under the みほん stamp and not read at all.
    r = official("my_number_card", parse_my_number_card)
    assert values(r)["expiry_date"] == "2025-03-31"
    assert not r["fields"]["expiry_date"]["notes"]  # found next to まで有効, not guessed


def test_official_driver_license():
    # 338px-wide specimen: 交付 and the era of the issue date are misread, so only the number comes out.
    r = official("driver_license", parse_driver_license)
    assert values(r)["license_number"] == "450599999940"  # 45 = 神奈川
    assert not [w for w in r["warnings"] if "運転免許証" in w]  # 公安委員会 identifies it
