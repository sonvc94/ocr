"""document=auto: detect.py on the real OCR of the official specimens, and the pipeline's auto flow with OCR stubbed."""

import json
from pathlib import Path

import numpy as np
import pytest

from app import pipeline
from app.detect import detect_document
from app.ocr.types import OcrBox

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_boxes(name: str) -> list[OcrBox]:
    d = json.loads((FIXTURES / name).read_text())
    lines = d["lines"] if isinstance(d, dict) else d
    return [OcrBox(l["text"], l["score"], tuple(l["box"])) for l in lines]


@pytest.mark.parametrize(
    "fixture, document",
    [
        ("moj_specimen_ocr.json", "jp_residence"),
        ("isa_residence_card_new_2026_ocr.json", "jp_residence"),
        ("isa_specified_residence_card_2026_ocr.json", "jp_residence"),
        ("low_quality_specimen_ocr.json", "jp_residence"),
        ("official_my_number_card_ocr.json", "jp_mynumber"),
        ("official_driver_license_ocr.json", "jp_driver_license"),  # 運転免許証 (vertical) not read: 公安委員会 + 第…号
        ("official_passport_2025_ocr.json", "jp_passport"),
        ("official_passport_2020_ocr.json", "jp_passport"),
        ("official_health_insurance_shikaku_kakuninsho_ocr.json", "jp_health_insurance"),
        ("official_special_permanent_resident_ocr.json", "jp_special_permanent"),
        ("official_special_permanent_resident_2026_ocr.json", "jp_special_permanent"),
        ("official_special_permanent_resident_specified_2026_ocr.json", "jp_special_permanent"),
        ("official_driving_history_ocr.json", "jp_driving_history"),  # also has 公安委員会 / 第…号 / 二・小・原
        ("official_driving_history_aichi_ocr.json", "jp_driving_history"),  # 298px; OCR reads 運転経歷 (traditional 歷)
        ("official_juki_card_ocr.json", "jp_juki_card"),
        ("official_juki_card_yokohama_ocr.json", "jp_juki_card"),  # 住民基本台帐力一ド
        ("official_resident_record_ocr.json", "jp_resident_record"),
        ("official_pension_notice_ocr.json", "jp_pension_book"),
    ],
)
def test_detects_official_specimens(fixture, document):
    d = detect_document(fixture_boxes(fixture))
    assert d.document == document, d.scores
    assert d.confident, d.scores


def box(text: str, y: float = 0) -> OcrBox:
    return OcrBox(text, 0.99, (0, y, 300, y + 40))


def test_nothing_recognisable():
    d = detect_document([box("氏名 山田 太郎"), box("住所 東京都千代田区", 60), box("2030年1月1日まで有効", 120)])
    assert d.document is None and not d.confident and not d.guessed


def test_guess_from_card_number_shape():
    # title and labels not read, only the residence card number
    d = detect_document([box("氏名 NGUYEN VAN A"), box("AB12345678CD", 60)])
    assert d.document == "jp_residence" and d.guessed and not d.confident


def test_guess_from_one_label():
    d = detect_document([box("氏名 山田 太郎"), box("在留資格 留学", 60)])  # 2 < MIN_SCORE
    assert d.document == "jp_residence" and d.guessed


def test_no_guess_on_a_tie():
    d = detect_document([box("記号 123"), box("301234567890", 60)])  # 記号 1 vs 12 digits 1
    assert d.document is None


def test_close_scores_are_not_confident():
    d = detect_document([box("運転免許証"), box("個人番号カード", 60)])  # 3 vs 3
    assert d.document is not None and not d.confident


def test_simplified_kanji_still_counts():
    assert detect_document([box("东京都公安委员会"), box("第 301234567890 号", 60)]).document == "jp_driver_license"


# --- pipeline.extract(document="auto") with the OCR and the card crop stubbed ---------------------------

def stub_pipeline(monkeypatch, texts_by_call):
    calls = []

    def fake_ocr(img, engine, lang):
        calls.append(img.shape)
        texts = texts_by_call[len(calls) - 1]
        return [box(t, 60 * i) for i, t in enumerate(texts)], img, 0.0, "stub", None

    monkeypatch.setattr(pipeline, "_ocr", fake_ocr)
    monkeypatch.setattr(pipeline, "normalize_card", lambda img: (np.zeros((1009, 1600, 3), np.uint8), True))
    return calls


def test_auto_parses_with_detected_document(monkeypatch):
    calls = stub_pipeline(monkeypatch, [["健康保険 被保険者証", "交付年月日 令和5年4月1日", "保険者名称 全国健康保険協会"]])
    result, _ = pipeline.extract(np.zeros((800, 1200, 3), np.uint8), (1200, 800), document="auto")
    assert result["document"] == "jp_health_insurance" and result["document_type"] == "health_insurance_card"
    assert result["document_detection"]["detected"] == "jp_health_insurance"
    assert result["fields"]["issue_date"]["value"] == "2023-04-01"
    assert len(calls) == 1 and result["ocr"]["card_cropped"]


def test_auto_passport_rereads_uncropped_image(monkeypatch):
    mrz = "TR12345672JPN9001011F3404012<<<<<<<<<<<<<<04"
    calls = stub_pipeline(monkeypatch, [["P<JPNNIHON<<HANAKO", mrz], ["日本国 JAPAN 旅券 PASSPORT", "P<JPNNIHON<<HANAKO", mrz]])
    result, img = pipeline.extract(np.zeros((800, 1200, 3), np.uint8), (1200, 800), document="auto")
    assert result["document"] == "jp_passport" and result["fields"]["passport_number"]["value"] == "TR1234567"
    assert calls == [(1009, 1600, 3), (800, 1200, 3)]  # 2nd OCR on the original, not the ID-1 crop
    assert not result["ocr"]["card_cropped"] and img.shape == (800, 1200, 3)


def test_auto_unknown_returns_ocr_text(monkeypatch):
    stub_pipeline(monkeypatch, [["氏名 山田 太郎", "住所 東京都千代田区"]])
    result, _ = pipeline.extract(np.zeros((800, 1200, 3), np.uint8), (1200, 800), document="auto")
    assert result["document"] is None and result["document_type"] is None and result["fields"] == {}
    assert "山田" in result["full_text"] and len(result["ocr"]["lines"]) == 2
    assert result["document_detection"]["detected"] is None
    assert result["warnings"] == [pipeline.UNKNOWN_WARNING]


def test_auto_guess_parses_with_guessed_document(monkeypatch):
    stub_pipeline(monkeypatch, [["氏名 NGUYEN VAN A", "AB12345678CD"]])
    result, _ = pipeline.extract(np.zeros((800, 1200, 3), np.uint8), (1200, 800), document="auto")
    assert result["document"] == "jp_residence" and result["document_detection"]["guessed"]
    assert result["fields"]["card_number"]["value"] == "AB12345678CD"
    assert any("đoán" in w for w in result["warnings"])


def test_explicit_document_has_no_detection(monkeypatch):
    stub_pipeline(monkeypatch, [["運転免許証", "交付 令和03年05月10日 12345", "第 301234567890 号"]])
    result, _ = pipeline.extract(np.zeros((800, 1200, 3), np.uint8), (1200, 800), document="jp_driver_license")
    assert result["document"] == "jp_driver_license" and "document_detection" not in result
