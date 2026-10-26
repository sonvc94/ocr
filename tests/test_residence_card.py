"""Parser tests on hand-written OCR output (no Paddle needed)."""

from app.residence_card import OcrBox, group_rows, parse_residence_card


def line(text: str, x: float, y: float, score: float = 0.98, w: float = 300, h: float = 40) -> OcrBox:
    return OcrBox(text=text, score=score, box=(x, y, x + w, y + h))


CARD = [
    line("在留カード", 60, 40),
    line("番号", 980, 50, w=60),
    line("AB12345678CD", 1060, 46),
    line("氏名", 60, 160, w=60),
    line("NGUYEN VAN AN", 260, 158, w=500),
    line("NAME", 60, 196, w=60, h=20),
    line("生年月日", 60, 250, w=120),
    line("1995年04月12日", 260, 248),
    line("性別", 640, 250, w=60),
    line("男M.", 720, 248, w=80),
    line("国籍・地域", 860, 250, w=150),
    line("ベトナム", 1020, 248, w=150),
    line("住居地", 60, 340, w=90),
    line("東京都新宿区西新宿二丁目8番1号", 260, 338, w=700),
    line("在留資格", 60, 440, w=120),
    line("技術・人文知識・国際業務", 260, 436, w=600),
    line("就労制限の有無", 60, 540, w=200),
    line("在留資格に基づく就労活動のみ可", 320, 538, w=600),
    line("在留期間(満了日)", 60, 620, w=260),
    line("5年(2029年06月30日)", 360, 618, w=400),
    line("許可の種類", 60, 710, w=150),
    line("在留期間更新許可(東京出入国在留管理局長)", 300, 708, w=800),
    line("許可年月日", 60, 800, w=150),
    line("2024年06月20日", 300, 798),
    line("交付年月日", 760, 800, w=150),
    line("2024年06月30日", 930, 798),
    line("このカードは2029年06月30日まで有効です。", 60, 900, w=900),
]


def values(result: dict) -> dict:
    return {k: v["value"] for k, v in result["fields"].items()}


def test_full_card():
    r = parse_residence_card(CARD)
    assert values(r) == {
        "card_number": "AB12345678CD",
        "name": "NGUYEN VAN AN",
        "date_of_birth": "1995-04-12",
        "permission_date": "2024-06-20",
        "issue_date": "2024-06-30",
        "sex": "M",
        "nationality": "ベトナム",
        "address": "東京都新宿区西新宿二丁目8番1号",
        "status_of_residence": "技術・人文知識・国際業務",
        "work_restriction": "在留資格に基づく就労活動のみ可",
        "period_of_stay": "5年",
        "expiration_date": "2029-06-30",
        "permission_type": "在留期間更新許可",
        "issuing_authority": "東京出入国在留管理局長",
        "valid_until": "2029-06-30",
    }
    assert r["warnings"] == []
    assert not any(f["needs_review"] for f in r["fields"].values())


def test_fullwidth_and_ocr_confusions():
    # Full-width characters and "I" read instead of "1"
    card = [line("ＡＢＩ２３４５６７８ＣＤ", 1060, 46) if b.text == "AB12345678CD" else b for b in CARD]
    f = parse_residence_card(card)["fields"]["card_number"]
    assert f["value"] == "AB12345678CD"
    assert f["needs_review"]  # auto-corrected values are flagged


def test_low_confidence_flags_review():
    card = [line("NGUYEN VAN AN", 260, 158, w=500, score=0.6) if b.text == "NGUYEN VAN AN" else b for b in CARD]
    f = parse_residence_card(card)["fields"]["name"]
    assert f["value"] == "NGUYEN VAN AN"
    assert f["needs_review"]


def test_value_on_next_row():
    # Address wrapped below its label
    card = [b for b in CARD if not b.text.startswith("東京都")] + [line("東京都新宿区西新宿二丁目8番1号", 60, 385, w=700)]
    assert parse_residence_card(card)["fields"]["address"]["value"] == "東京都新宿区西新宿二丁目8番1号"


def test_work_restriction_snapped_to_official_value():
    card = [line("在留資格に基づく就労活動のみ司", 320, 538, w=600) if "就労活動" in b.text else b for b in CARD]
    f = parse_residence_card(card)["fields"]["work_restriction"]
    assert f["value"] == "在留資格に基づく就労活動のみ可"
    assert f["needs_review"]


def test_not_a_residence_card():
    r = parse_residence_card([line("運転免許証", 0, 0)])
    assert r["warnings"]
    assert all(v is None for v in values(r).values())


def test_group_rows_orders_left_to_right():
    rows = group_rows([line("B", 400, 102), line("A", 10, 100), line("C", 10, 200)])
    assert [[b.text for b in r] for r in rows] == [["A", "B"], ["C"]]


def test_ocr_confusables():
    replace = {
        "在留資格": "在留资格",  # simplified Chinese 资
        "ベトナム": "ベ卜ナム",  # kanji 卜 for katakana ト
        "東京都新宿区西新宿二丁目8番1号": "東京都新宿区西新宿ニ丁目8番1号",  # katakana ニ for 二
        "生年月日": "生年月日 DATEOFBIRTH",
    }
    card = [line(replace[b.text], *b.box[:2], w=b.box[2] - b.box[0]) if b.text in replace else b for b in CARD]
    v = values(parse_residence_card(card))
    assert v["status_of_residence"] == "技術・人文知識・国際業務"
    assert v["nationality"] == "ベトナム"
    assert v["address"] == "東京都新宿区西新宿二丁目8番1号"
    assert v["date_of_birth"] == "1995-04-12"


def test_moj_specimen_card():
    """Real PP-OCRv5 output for the Ministry of Justice specimen card (見本, TURNER ELIZABETH)."""
    import json
    from pathlib import Path

    lines = json.loads((Path(__file__).parent / "fixtures/moj_specimen_ocr.json").read_text())
    r = parse_residence_card([OcrBox(l["text"], l["score"], tuple(l["box"])) for l in lines])
    assert values(r) == {
        "card_number": "AB12345678CD",
        "name": "TURNER ELIZABETH",
        "date_of_birth": "1985-12-31",
        "permission_date": "2014-06-10",
        "issue_date": "2014-06-10",
        "sex": "F",
        "nationality": "米国",
        "address": "東京都千代田区霞が関1丁目1番1号霞が関八ツ202号",  # OCR misread of ハイツ, kept as-is
        "status_of_residence": "留学",
        "work_restriction": "就労不可",
        "period_of_stay": "4年3月",
        "expiration_date": "2018-10-20",
        "permission_type": "在留期間更新許可",
        "issuing_authority": "東京入国管理局長",
        "valid_until": "2018-10-20",
    }


def test_low_quality_image_uses_english_anchors_and_flags_quality():
    """Real OCR output of a blurry/watermarked specimen image where every kanji label is garbled."""
    import json
    from pathlib import Path

    lines = json.loads((Path(__file__).parent / "fixtures/low_quality_specimen_ocr.json").read_text())
    r = parse_residence_card([OcrBox(l["text"], l["score"], tuple(l["box"])) for l in lines])
    v = values(r)
    assert r["quality"]["level"] == "low"
    assert {k: v[k] for k in ("name", "date_of_birth", "sex", "period_of_stay", "expiration_date",
                              "permission_date", "issue_date", "work_restriction", "valid_until")} == {
        "name": "TURNER ELIZABETH",
        "date_of_birth": "1985-12-31",
        "sex": "F",
        "period_of_stay": "4年3月",
        "expiration_date": "2018-10-20",
        "permission_date": "2014-06-10",
        "issue_date": "2014-06-10",
        "work_restriction": "就労不可",
        "valid_until": "2018-10-20",
    }
    assert v["nationality"] is None  # only stray English text where the value should be
    assert all(f["needs_review"] for k, f in r["fields"].items() if k not in ("card_number", "valid_until"))


def test_good_image_quality_ok():
    r = parse_residence_card(CARD)
    assert r["quality"]["level"] == "ok"
    assert r["labels_from_english_anchor"] == []


def _fixture(name: str) -> dict:
    import json
    from pathlib import Path

    lines = json.loads((Path(__file__).parent / "fixtures" / name).read_text())
    return parse_residence_card([OcrBox(l["text"], l["score"], tuple(l["box"])) for l in lines])


def test_isa_new_2026_design():
    """Official specimen of the card design issued from 2026-06-14 (no permission/issue rows)."""
    r = _fixture("isa_residence_card_new_2026_ocr.json")
    assert r["card_design"] == "2026"
    v = values(r)
    assert {k: v[k] for k in ("card_number", "name", "date_of_birth", "sex", "nationality",
                              "status_of_residence", "work_restriction", "expiration_date", "valid_until")} == {
        "card_number": "AB12345678CD",
        "name": "TURNER ELIZABETH",
        "date_of_birth": "1985-12-31",
        "sex": "F",
        "nationality": "米国",
        "status_of_residence": "永住者の配偶者等",
        "work_restriction": "就労制限なし",
        "expiration_date": "2030-12-05",
        "valid_until": "2030-12-05",
    }
    for key in ("period_of_stay", "permission_type", "issuing_authority", "permission_date", "issue_date"):
        assert v[key] is None and not r["fields"][key]["needs_review"]


def test_isa_specified_card_is_flagged_unsupported():
    r = _fixture("isa_specified_residence_card_2026_ocr.json")
    assert r["card_design"] == "specified_2026"
    assert any("特定在留カード" in w for w in r["warnings"])
    assert all(f["needs_review"] for f in r["fields"].values())
