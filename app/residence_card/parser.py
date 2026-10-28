"""Rule-based field extraction for the front side of a Japanese residence card (在留カード).

Input is the list of OCR text boxes (text, score, box). Boxes are grouped into visual
rows, joined into one normalized text, and each field is taken as the span between
its label and the next label found on the card (mode=label).

mode=zone / hybrid also read each field from its fixed position on the card (zones.py), once the
card template has been located in the image (registration.py).
"""

from __future__ import annotations

import re

from ..card_core.field import Field
from ..card_core.layout import Document, drop_non_text
from ..card_core.registration import register
from ..card_core.zones import ZoneSpec, extract_zone_fields, merge, zones_px
from ..ocr.types import OcrBox
from .checks import assess_quality, card_design, cross_check
from .fields import extract_fields, label_positions
from .patterns import (
    DATE_RE,
    ENGLISH_ANCHORS,
    ENGLISH_SUBLABELS,
    FIELD_LABELS,
    LABELS,
    NOT_PRINTED_SINCE_2026,
    RESIDENCE_CARD_TITLE,
    normalize,
)
from .templates import TEMPLATES

MODES = ("label", "zone", "hybrid")

ZONE_SPEC = ZoneSpec(
    normalize=normalize,
    labels=(re.compile("|".join(f"(?:{p})" for p in LABELS.values())), ENGLISH_SUBLABELS),
    unit=re.compile(r"[0-9０-９]+(?:[年月日][0-9０-９]+)*[年月日]?|[A-Za-z][A-Za-z.,'\-]*|.", re.S),
    markers_only=re.compile(r"[YMD.\s]{1,6}"),  # the Y M D unit marks printed under dates
    label_lang="jp",
    parse=lambda doc: extract_fields(doc, label_positions(doc.text))[0],
)

# Fields whose label belongs to another field (both come out of the same segment).
DERIVED_FROM = {"expiration_date": "period_of_stay", "issuing_authority": "permission_type"}
# Kanji is what breaks first on bad images; these are never let through silently on a low-quality image.
KANJI_FIELDS = ("nationality", "address", "status_of_residence", "work_restriction", "permission_type", "issuing_authority")


def parse_residence_card(
    boxes: list[OcrBox], page_size: tuple[int, int] | None = None, cropped: bool = False, mode: str = "label"
) -> dict:
    """`page_size` (width, height) is the image the boxes refer to; `cropped` tells whether it is the card
    already cut out and flattened. Both only matter for mode=zone/hybrid."""
    boxes = drop_non_text(boxes)
    ocr_boxes = boxes
    ocr_doc = Document(boxes, normalize)
    labels = label_positions(ocr_doc.text)
    jp_labels_found = len(labels.keys() & FIELD_LABELS)
    missing = [k for k in ENGLISH_ANCHORS if k not in labels]
    anchored: set[str] = set()
    if missing:
        boxes, anchored = _anchor_labels(boxes, missing)
    doc = Document(boxes, normalize) if anchored else ocr_doc
    labels = label_positions(doc.text)
    warnings: list[str] = []

    if not RESIDENCE_CARD_TITLE.search(doc.text):
        warnings.append("Không tìm thấy chữ 在留カード / RESIDENCE CARD — ảnh có thể không phải thẻ cư trú.")

    fields, guessed = extract_fields(doc, labels)

    design = card_design(doc.text, labels)
    layout = {"mode": mode, "registration": None, "zones_px": {}}
    if mode != "label":
        reg = register(ocr_boxes, TEMPLATES[design], page_size, cropped, normalize) if design in TEMPLATES else None
        if reg is None:
            warnings.append("Không định vị được mẫu thẻ trong ảnh (quá ít nhãn đọc được): chỉ dùng kết quả theo nhãn.")
        else:
            layout["registration"] = reg.to_dict()
            layout["zones_px"] = zones_px(reg, TEMPLATES[design])
            zone_fields = extract_zone_fields(ocr_boxes, reg, TEMPLATES[design], ZONE_SPEC)
            if mode == "zone":
                fields = {k: zone_fields.get(k, Field(source="zone")) for k in fields}
            else:
                fields = merge(fields, zone_fields)

    if design == "2026":
        for key in NOT_PRINTED_SINCE_2026:
            fields[key] = Field(notes=["Mẫu thẻ từ 14/06/2026 không in mục này (chỉ lưu trong chip IC)."], needs_review=False)
            guessed.discard(key)
    elif design == "specified_2026":
        warnings.append("Đây là 特定在留カード (thẻ cư trú gộp My Number), bố cục khác hẳn — demo chưa hỗ trợ, kết quả không đáng tin.")

    for key, f in fields.items():
        if f.value is None or f.source == "zone":
            continue
        if DERIVED_FROM.get(key, key) in anchored:
            f.notes.append("Nhãn tiếng Nhật đọc lỗi, vị trí xác định qua nhãn tiếng Anh.")
            f.needs_review = True
        if DERIVED_FROM.get(key, key) in guessed:
            f.notes.append("Không thấy nhãn, đoán theo mẫu chữ.")
            f.needs_review = True

    quality = assess_quality(ocr_doc, jp_labels_found)
    if design == "specified_2026":
        for f in fields.values():
            f.needs_review = True
    if quality["level"] == "low":
        for key in KANJI_FIELDS:
            fields[key].needs_review = True

    warnings += cross_check(fields)

    return {
        "document_type": "residence_card",
        "side": "front",
        "card_design": design,
        "fields": {k: v.to_dict() for k, v in fields.items()},
        "quality": quality,
        "warnings": warnings,
        "mean_ocr_confidence": None if ocr_doc.mean_score is None else round(ocr_doc.mean_score, 4),
        "labels_found": sorted(labels),
        "labels_from_english_anchor": sorted(anchored),
        "layout": layout,
        "full_text": doc.text,
    }


def _anchor_labels(boxes: list[OcrBox], missing: list[str]) -> tuple[list[OcrBox], set[str]]:
    """Put a canonical Japanese label where an unreadable one sits, using the English sub-label below it.

    The box directly above the English sub-label (same left edge) is taken to be the garbled
    Japanese label and its text is replaced; if there is none, a virtual label box is inserted
    on the value's row.
    """
    boxes = list(boxes)
    anchored: set[str] = set()
    for key in missing:
        pattern, label = ENGLISH_ANCHORS[key]
        anchor = next((b for b in boxes if re.search(pattern, normalize(b.text).upper())), None)
        if anchor is None:
            continue
        x1, y1, x2, _ = anchor.box
        h = anchor.height
        above = [
            (i, b) for i, b in enumerate(boxes)
            if b is not anchor and abs(b.box[0] - x1) < 1.5 * h and b.box[3] <= y1 + 0.5 * h
            and y1 - b.box[3] < 1.5 * h and len(b.text) <= 10 and not re.search(r"[A-Z]{3}", b.text)
            and not DATE_RE.search(normalize(b.text))
        ]
        if above:
            i, b = max(above, key=lambda ib: ib[1].box[3])
            boxes[i] = OcrBox(label, b.score, b.box, virtual=True)
        else:
            boxes.append(OcrBox(label, 1.0, (x1, y1 - 1.2 * h, x1 + h, y1 - 0.2 * h), virtual=True))
        anchored.add(key)
    return boxes, anchored
