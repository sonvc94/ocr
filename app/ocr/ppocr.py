"""PP-OCR engine: run the shared pipeline for the card's language and straighten tilted text lines."""

from __future__ import annotations

import numpy as np

from ..preprocess import estimate_skew, rotate
from .ppocr_model import predict
from .types import OcrBox

# Below this tilt the axis-aligned boxes are already good enough; above the max it is not a tilt
# (the 90/180/270° cases are handled by the orientation classifier).
DESKEW_MIN_DEG = 1.0
DESKEW_MAX_DEG = 30.0


def run_ocr(img: np.ndarray, lang: str = "ja") -> tuple[list[OcrBox], np.ndarray, float]:
    """Return the text boxes, the image they refer to (rotated if orientation/tilt was corrected)
    and the tilt in degrees that was straightened (0 if none).

    A tilted photo whose card edge was not found is straightened here: the quads from text
    detection give the tilt, the image is rotated and the quads mapped into it, so each line's
    box is tight and rows group correctly. Recognition itself already reads the tilted quads.
    """
    lines: list[tuple[str, float, np.ndarray]] = []
    used = img
    for res in predict(img, lang):
        doc_pre = res.get("doc_preprocessor_res")
        if doc_pre is not None and doc_pre.get("output_img") is not None:
            used = doc_pre["output_img"]
        for text, score, poly in zip(res["rec_texts"], res["rec_scores"], res["rec_polys"]):
            if text.strip():
                lines.append((text, float(score), np.asarray(poly, dtype=np.float32).reshape(-1, 2)))

    skew = estimate_skew([p for _, _, p in lines])
    if DESKEW_MIN_DEG <= abs(skew) <= DESKEW_MAX_DEG:
        used, m = rotate(used, skew)
        lines = [(t, s, p @ m[:, :2].T + m[:, 2]) for t, s, p in lines]
    else:
        skew = 0.0
    boxes = [
        OcrBox(text=t, score=s, box=(float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())))
        for t, s, p in lines
    ]
    return boxes, used, skew
