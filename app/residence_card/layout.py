"""From OCR boxes to card text: drop non-text boxes, group boxes into visual rows, flatten to one string."""

from __future__ import annotations

from ..ocr.types import OcrBox
from .patterns import normalize


def drop_non_text(boxes: list[OcrBox]) -> list[OcrBox]:
    """Text lines on the card are all about the same height; a box several times taller is the photo or a seal."""
    if len(boxes) < 5:
        return boxes
    median_h = sorted(b.height for b in boxes)[len(boxes) // 2]
    return [b for b in boxes if b.height <= 4 * median_h]


def _rows_at_slope(boxes: list[OcrBox], slope: float) -> list[list[OcrBox]]:
    """Group boxes whose centers lie on the same line of the given slope (dy/dx)."""
    rows: list[list[OcrBox]] = []
    for b in sorted(boxes, key=lambda b: b.cy - slope * b.cx):
        if rows:
            last = rows[-1]
            ref_y = sum(x.cy - slope * x.cx for x in last) / len(last)
            ref_h = min(min(x.height for x in last), b.height)
            if abs(b.cy - slope * b.cx - ref_y) < ref_h * 0.5:
                last.append(b)
                continue
        rows.append([b])
    return rows


# A tilted photo (when the card edge was not found to flatten it) shifts a row by tens of pixels
# across the card, splitting labels from their values. Rows are grouped along the slope that
# gives the fewest rows; it must beat horizontal by 2+ rows so straight cards are unaffected.
_SLOPES = [i * 0.005 for i in range(-36, 37)]  # up to ~10°


def group_rows(boxes: list[OcrBox]) -> list[list[OcrBox]]:
    """Group boxes lying on the same visual line (tolerating tilt), left to right inside each row."""
    rows = _rows_at_slope(boxes, 0.0)
    best = min((_rows_at_slope(boxes, s) for s in sorted(_SLOPES, key=abs)), key=len)
    if len(best) <= len(rows) - 2:
        rows = best
    return [sorted(r, key=lambda b: b.box[0]) for r in rows]


class Document:
    """Flattened card text with a char-span -> OCR score mapping for confidence lookup."""

    def __init__(self, boxes: list[OcrBox]):
        self.rows = group_rows(boxes)
        parts: list[str] = []
        self.spans: list[tuple[int, int, float]] = []
        self.ocr_scores = [b.score for b in boxes if not b.virtual]
        pos = 0
        for r_idx, row in enumerate(self.rows):
            if r_idx:
                parts.append("\n")
                pos += 1
            for b_idx, b in enumerate(row):
                if b_idx:
                    parts.append(" ")
                    pos += 1
                t = normalize(b.text)
                parts.append(t)
                if not b.virtual:
                    self.spans.append((pos, pos + len(t), b.score))
                pos += len(t)
        self.text = "".join(parts)

    def score(self, start: int, end: int) -> float | None:
        scores = [s for a, b, s in self.spans if a < end and b > start]
        return min(scores) if scores else None

    @property
    def mean_score(self) -> float | None:
        return sum(self.ocr_scores) / len(self.ocr_scores) if self.ocr_scores else None
