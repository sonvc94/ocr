"""Rule-based field extraction for the front side of a Japanese residence card (在留カード).

Input is the list of OCR text boxes (text, score, box). Boxes are grouped into visual
rows, joined into one normalized text, and each field is taken as the span between
its label and the next label found on the card.
"""

from __future__ import annotations

import re

from ..ocr.types import OcrBox
from .checks import assess_quality, card_design, cross_check
from .fields import Field, Labels, extract_fields
from .layout import Document, drop_non_text
from .patterns import (
    DATE_RE,
    ENGLISH_ANCHORS,
    FIELD_LABELS,
    LABELS,
    NOT_PRINTED_SINCE_2026,
    RESIDENCE_CARD_TITLE,
    normalize,
)

# Fields whose label belongs to another field (both come out of the same segment).
DERIVED_FROM = {"expiration_date": "period_of_stay", "issuing_authority": "permission_type"}
# Kanji is what breaks first on bad images; these are never let through silently on a low-quality image.
KANJI_FIELDS = ("nationality", "address", "status_of_residence", "work_restriction", "permission_type", "issuing_authority")


def parse_residence_card(boxes: list[OcrBox]) -> dict:
    boxes = drop_non_text(boxes)
    ocr_doc = Document(boxes)
    labels = _label_positions(ocr_doc.text)
    jp_labels_found = len(labels.keys() & FIELD_LABELS)
    missing = [k for k in ENGLISH_ANCHORS if k not in labels]
    anchored: set[str] = set()
    if missing:
        boxes, anchored = _anchor_labels(boxes, missing)
    doc = Document(boxes) if anchored else ocr_doc
    labels = _label_positions(doc.text)
    warnings: list[str] = []

    if not RESIDENCE_CARD_TITLE.search(doc.text):
        warnings.append("Không tìm thấy chữ 在留カード / RESIDENCE CARD — ảnh có thể không phải thẻ cư trú.")

    fields, guessed = extract_fields(doc, labels)

    design = card_design(doc.text, labels)
    if design == "2026":
        for key in NOT_PRINTED_SINCE_2026:
            fields[key] = Field(notes=["Mẫu thẻ từ 14/06/2026 không in mục này (chỉ lưu trong chip IC)."], needs_review=False)
            guessed.discard(key)
    elif design == "specified_2026":
        warnings.append("Đây là 特定在留カード (thẻ cư trú gộp My Number), bố cục khác hẳn — demo chưa hỗ trợ, kết quả không đáng tin.")

    for key, f in fields.items():
        if f.value is None:
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
        "full_text": doc.text,
    }


def _label_positions(text: str) -> Labels:
    found: Labels = {}
    for key, pattern in LABELS.items():
        m = re.search(pattern, text)
        if m:
            found[key] = (m.start(), m.end())
    return found


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
