"""One extracted field and the rules that decide when it needs a human look."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

CONFIDENCE_THRESHOLD = 0.85


@dataclass
class Field:
    value: str | None = None
    raw: str | None = None
    confidence: float | None = None
    needs_review: bool = True
    notes: list[str] = field(default_factory=list)
    source: str = "label"  # label | zone | label+zone (see zones.py)

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "raw": self.raw,
            "confidence": None if self.confidence is None else round(self.confidence, 4),
            "needs_review": self.needs_review,
            "notes": self.notes,
            "source": self.source,
        }


def finish(f: Field, confidence: float | None) -> Field:
    f.confidence = confidence
    f.needs_review = f.value is None or confidence is None or confidence < CONFIDENCE_THRESHOLD or bool(f.notes)
    return f


def snap(f: Field, text: str, choices: list[str]) -> None:
    """Set f.value to the closest official wording; flag it when OCR text had to be corrected."""
    best = difflib.get_close_matches(text, choices, n=1, cutoff=0.6)
    if best:
        f.value = best[0]
        if best[0] != text:
            f.notes.append("Đã chuẩn hoá theo danh sách giá trị chính thức.")
    else:
        f.value = text or None
