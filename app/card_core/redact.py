"""Hide My Number (個人番号, 12 digits) from the OCR text before anything else sees it.

The My Number Act (番号法) restricts collecting the number. It is not printed on the documents read here except the
certificate of residence (住民票の写し, when the holder asks for it); the My Number card front does not carry it.
"""

from __future__ import annotations

import re
from dataclasses import replace

from ..ocr.types import OcrBox

MASK = "*"
LABEL_RE = re.compile(r"個\s*人\s*番\s*号")
# 12 digits, possibly grouped 4-4-4 by spaces or hyphens.
NUMBER_RE = re.compile(r"(?<![0-9０-９])[0-9０-９]{4}[\s\-－ー]?[0-9０-９]{4}[\s\-－ー]?[0-9０-９]{4}(?![0-9０-９])")


def _mask(text: str) -> str:
    return NUMBER_RE.sub(lambda m: re.sub(r"[0-9０-９]", MASK, m.group(0)), text)


def redact_my_number(boxes: list[OcrBox], every_number: bool = False) -> tuple[list[OcrBox], list[OcrBox]]:
    """(boxes with the number replaced by ****, the boxes that were changed).

    `every_number`: mask every 12-digit number (住民票: no other 12-digit number is printed on it). Otherwise only
    numbers in a box containing 個人番号, right of it on the same line, or just below it (table cell).
    """
    labels = [b for b in boxes if LABEL_RE.search(b.text)]
    out, changed = [], []
    for b in boxes:
        near_label = any(b is lab or _beside(b, lab) or _below(b, lab) for lab in labels)
        if (every_number or near_label) and NUMBER_RE.search(b.text):
            nb = replace(b, text=_mask(b.text))
            out.append(nb)
            changed.append(nb)
        else:
            out.append(b)
    return out, changed


def _beside(b: OcrBox, lab: OcrBox) -> bool:
    return abs(b.cy - lab.cy) < lab.height and b.box[0] >= lab.box[0]


def _below(b: OcrBox, lab: OcrBox) -> bool:
    overlaps = b.box[0] < lab.box[2] and b.box[2] > lab.box[0]
    return overlaps and 0 < b.cy - lab.cy <= 2 * lab.height


def redact_text(text: str) -> str:
    """Mask every 12-digit number in free text (VL blocks of a 住民票)."""
    return _mask(text)
