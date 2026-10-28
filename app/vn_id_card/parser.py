"""Rule-based field extraction for the front of the Vietnamese identity cards (thẻ căn cước 2024, chip CCCD 2021).

Same flow as residence_card: OCR boxes grouped into rows, flattened to one text, each field taken as the
span between its label and the next label (mode=label); mode=zone/hybrid also read fields by position
once the card template is located in the image (card_core.registration / card_core.zones).
"""

from __future__ import annotations

import re

from ..card_core.field import Field
from ..card_core.layout import Document, drop_non_text
from ..card_core.registration import register
from ..card_core.zones import ZoneSpec, extract_zone_fields, merge, zones_px
from ..ocr.types import OcrBox
from .checks import assess_quality, cross_check
from .fields import FIELD_KEYS, extract_fields, label_positions
from .patterns import CCCD_TITLE_RE, DESIGNS, ENGLISH_SUBLABELS, LABELS, TITLE_RE, fold, normalize
from .templates import TEMPLATES

MODES = ("label", "zone", "hybrid")
# Diacritics are what breaks first on bad images; these are never let through silently on a low-quality image.
DIACRITIC_FIELDS = ("full_name", "nationality", "place_of_origin", "place_of_residence")


def _zone_spec(design: str) -> ZoneSpec:
    return ZoneSpec(
        normalize=normalize,
        labels=(re.compile("|".join(f"(?:{p.pattern})" for p in LABELS[design].values()), re.IGNORECASE | re.MULTILINE), ENGLISH_SUBLABELS),
        unit=re.compile(r"\d{1,2}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*\d{4}|\d+|[^\W\d_]+|.", re.S),
        markers_only=None,
        label_lang="vi",
        parse=lambda doc: extract_fields(doc, label_positions(doc.text, design)[0], design)[0],
    )


ZONE_SPECS = {d: _zone_spec(d) for d in DESIGNS}


def card_design(text: str) -> str:
    """The 2021 card's title is "CĂN CƯỚC CÔNG DÂN / Citizen Identity Card"; the 2024 one "CĂN CƯỚC / Identity Card"."""
    return "cccd_2021" if CCCD_TITLE_RE.search(text) else "2024"


def _anchor_text(text: str) -> str:
    """Anchors are compared without diacritics: OCR gets them wrong far more often than the letters."""
    return fold(normalize(text))


def parse_vn_id_card(
    boxes: list[OcrBox], page_size: tuple[int, int] | None = None, cropped: bool = False, mode: str = "label"
) -> dict:
    """`page_size` (width, height) is the image the boxes refer to; `cropped` tells whether it is the card
    already cut out and flattened. Both only matter for mode=zone/hybrid."""
    boxes = drop_non_text(boxes)
    doc = Document(boxes, normalize)
    design = card_design(doc.text)
    labels, vietnamese = label_positions(doc.text, design)
    warnings: list[str] = []

    if not TITLE_RE.search(doc.text):
        warnings.append("Không tìm thấy chữ CĂN CƯỚC / IDENTITY CARD — ảnh có thể không phải thẻ căn cước.")

    fields, guessed = extract_fields(doc, labels, design)

    template = TEMPLATES[design]
    layout = {"mode": mode, "registration": None, "zones_px": {}}
    if mode != "label":
        reg = register(boxes, template, page_size, cropped, _anchor_text)
        if reg is None:
            warnings.append("Không định vị được mẫu thẻ trong ảnh (quá ít nhãn đọc được): chỉ dùng kết quả theo nhãn.")
        else:
            layout["registration"] = reg.to_dict()
            layout["zones_px"] = zones_px(reg, template)
            zone_fields = extract_zone_fields(boxes, reg, template, ZONE_SPECS[design])
            if mode == "zone":
                fields = {k: zone_fields.get(k, Field(source="zone")) for k in fields}
            else:
                fields = merge(fields, zone_fields)

    english_only = sorted(labels.keys() - vietnamese)
    for key, f in fields.items():
        if f.value is None or f.source == "zone":
            continue
        if key in english_only:
            f.notes.append("Nhãn tiếng Việt đọc lỗi, vị trí xác định qua nhãn tiếng Anh.")
            f.needs_review = True
        if key in guessed and f.source != "label+zone":  # its position on the card confirms the guess
            f.notes.append("Không thấy nhãn, đoán theo mẫu chữ.")
            f.needs_review = True

    quality = assess_quality(doc, len(vietnamese & set(FIELD_KEYS[design])), design)
    if quality["level"] == "low":
        for key in DIACRITIC_FIELDS:
            if key in fields:
                fields[key].needs_review = True

    warnings += cross_check(fields, design)

    return {
        "document_type": "vn_id_card",
        "side": "front",
        "card_design": design,
        "fields": {k: v.to_dict() for k, v in fields.items()},
        "quality": quality,
        "warnings": warnings,
        "mean_ocr_confidence": None if doc.mean_score is None else round(doc.mean_score, 4),
        "labels_found": sorted(labels),
        "labels_from_english_anchor": english_only,
        "layout": layout,
        "full_text": doc.text,
    }
