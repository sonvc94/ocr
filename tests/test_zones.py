"""mode=zone/hybrid: locating the card template from OCR lines and reading fields by position (no Paddle needed)."""

import json
import math
from pathlib import Path

from app.ocr.types import OcrBox
from app.residence_card import parse_residence_card
from app.card_core.registration import register
from app.residence_card.patterns import normalize
from app.residence_card.templates import TEMPLATES

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_boxes(name: str) -> list[OcrBox]:
    return [OcrBox(l["text"], l["score"], tuple(l["box"])) for l in json.loads((FIXTURES / name).read_text())]


def values(result: dict) -> dict:
    return {k: v["value"] for k, v in result["fields"].items()}


def moved(boxes: list[OcrBox], degrees: float, scale: float, dx: float, dy: float) -> list[OcrBox]:
    """The card photographed smaller, shifted and slightly tilted: line centers move, lines stay horizontal
    (as after PP-OCR's deskew)."""
    a = math.radians(degrees)
    out = []
    for b in boxes:
        cx, cy = b.cx, b.cy
        nx = scale * (cx * math.cos(a) - cy * math.sin(a)) + dx
        ny = scale * (cx * math.sin(a) + cy * math.cos(a)) + dy
        w, h = (b.box[2] - b.box[0]) * scale / 2, (b.box[3] - b.box[1]) * scale / 2
        out.append(OcrBox(b.text, b.score, (nx - w, ny - h, nx + w, ny + h)))
    return out


def test_zone_mode_matches_label_mode_on_specimens():
    # moj specimen: one OCR line spans date of birth + sex, another sex + nationality; both are split by position
    for name, size in (("moj_specimen_ocr.json", None), ("isa_residence_card_new_2026_ocr.json", (1600, 1000))):
        boxes = fixture_boxes(name)
        label = parse_residence_card(boxes)
        zone = parse_residence_card(boxes, page_size=size, mode="zone")
        assert values(zone) == values(label), name
        reg = zone["layout"]["registration"]
        assert reg["method"] == "anchors" and reg["residual"] < 0.01
        assert set(zone["layout"]["zones_px"]) == set(TEMPLATES[zone["card_design"]]["fields"])


def test_hybrid_marks_agreeing_fields():
    r = parse_residence_card(fixture_boxes("moj_specimen_ocr.json"), mode="hybrid")
    assert all(f["source"] == "label+zone" for f in r["fields"].values())
    assert r["fields"]["name"]["needs_review"] is False


def test_registration_follows_a_smaller_tilted_card():
    boxes = fixture_boxes("moj_specimen_ocr.json")
    expected = values(parse_residence_card(boxes))
    shifted = moved(boxes, degrees=3, scale=0.6, dx=300, dy=150)
    r = parse_residence_card(shifted, page_size=(1400, 1000), mode="zone")
    reg = r["layout"]["registration"]
    assert abs(reg["rotation_deg"] - 3) < 0.5
    assert 0.3 < reg["card_fraction"] < 0.5
    assert {k: values(r)[k] for k in ("card_number", "name", "date_of_birth", "address", "valid_until")} == {
        k: expected[k] for k in ("card_number", "name", "date_of_birth", "address", "valid_until")
    }


def test_hybrid_fills_a_field_whose_label_is_unreadable():
    boxes = [b for b in fixture_boxes("moj_specimen_ocr.json") if b.text not in ("生年月日", "DATE OF BIRTH")]
    assert parse_residence_card(boxes)["fields"]["date_of_birth"]["value"] is None
    f = parse_residence_card(boxes, mode="hybrid")["fields"]["date_of_birth"]
    assert f["value"] == "1985-12-31"
    assert f["source"] == "zone" and f["needs_review"] is True


def test_too_few_anchors_falls_back_to_labels():
    boxes = [OcrBox("在留カード", 0.99, (300, 20, 500, 60)), OcrBox("氏名", 0.99, (20, 100, 70, 130)),
             OcrBox("NGUYEN VAN AN", 0.99, (90, 100, 400, 130))]
    r = parse_residence_card(boxes, mode="zone")
    assert r["layout"]["registration"] is None
    assert r["fields"]["name"]["value"] == "NGUYEN VAN AN"
    assert any("Không định vị được" in w for w in r["warnings"])


def test_flattened_card_without_anchors_uses_the_crop():
    reg = register([], TEMPLATES["2012"], page_size=(1600, 1009), cropped=True, normalize=normalize)
    assert reg.method == "crop"
    assert register([], TEMPLATES["2012"], page_size=(1600, 1200), cropped=True, normalize=normalize) is None  # not the card's shape
