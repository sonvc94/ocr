"""The OCR line format shared by the engines and the parser."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OcrBox:
    text: str
    score: float
    box: tuple[float, float, float, float]  # x1, y1, x2, y2
    virtual: bool = False  # label inserted by the parser, not read by OCR

    @property
    def cy(self) -> float:
        return (self.box[1] + self.box[3]) / 2

    @property
    def cx(self) -> float:
        return (self.box[0] + self.box[2]) / 2

    @property
    def height(self) -> float:
        return self.box[3] - self.box[1]
