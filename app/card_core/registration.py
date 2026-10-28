"""Locate a card template in the OCR'd image: a transform from card coordinates to image pixels.

Two sources, best first:
- anchors: OCR lines whose text is a fixed print of the card (labels, titles) are matched to their
  template position, and a rotation + uniform scale + shift (or a perspective transform with enough
  anchors) is fitted with RANSAC. Works when the card edge was not found (close-up, tilted photo).
- crop: the image is the card already flattened by preprocess.normalize_card, so the template is just
  scaled to the image size. Used when too few anchors are readable.
"""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np

from ..ocr.types import OcrBox
from .templates import CARD_W, card_h

MIN_ANCHORS = 3  # two points always fit a similarity exactly: a third is needed to check the fit
MAX_RESIDUAL = 0.02  # mean anchor error, in card widths
MAX_ROTATION_DEG = 30.0
MIN_CARD_FRACTION = 0.2  # card width / image width
CROP_ASPECT_TOLERANCE = 0.02


@dataclass
class Registration:
    matrix: np.ndarray  # 3x3, card px -> image px
    method: str  # anchors | crop
    transform: str  # similarity | homography | scale
    anchors_used: int
    residual: float | None
    rotation_deg: float
    card_fraction: float | None

    def to_image(self, pts: np.ndarray) -> np.ndarray:
        return cv2.perspectiveTransform(np.asarray(pts, np.float64).reshape(-1, 1, 2), self.matrix).reshape(-1, 2)

    def to_card(self, pts: np.ndarray) -> np.ndarray:
        inv = np.linalg.inv(self.matrix)
        return cv2.perspectiveTransform(np.asarray(pts, np.float64).reshape(-1, 1, 2), inv).reshape(-1, 2)

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "transform": self.transform,
            "anchors_used": self.anchors_used,
            "residual": None if self.residual is None else round(self.residual, 4),
            "rotation_deg": round(self.rotation_deg, 1),
            "card_fraction": None if self.card_fraction is None else round(self.card_fraction, 2),
        }


def _compact(text: str, normalize: Callable[[str], str]) -> str:
    return re.sub(r"[\s・･·]", "", re.sub(r"[一ー-]", "ー", normalize(text))).upper()


def _is_anchor(text: str, anchor: str, normalize: Callable[[str], str]) -> bool:
    t, a = _compact(text, normalize), _compact(anchor, normalize)
    if len(a) <= 4:
        return t == a
    return difflib.SequenceMatcher(None, t, a).ratio() >= 0.85


def _corners(box) -> np.ndarray:
    x0, y0, x1, y1 = box
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], np.float64)


def _card_corners(template: dict) -> np.ndarray:
    return _corners((0, 0, CARD_W, card_h(template)))


def register(
    boxes: list[OcrBox], template: dict, page_size: tuple[int, int] | None, cropped: bool, normalize: Callable[[str], str]
) -> Registration | None:
    """The best acceptable registration, or None when the card cannot be located reliably.
    `normalize` is the card's text normalization, used to compare OCR lines with anchor texts."""
    reg = _from_anchors(boxes, template, page_size, normalize)
    if reg is None and cropped and page_size:
        reg = _from_crop(template, page_size)
    return reg


def _matches(boxes: list[OcrBox], template: dict, normalize: Callable[[str], str]) -> list[tuple[int, np.ndarray, np.ndarray]]:
    """(anchor index, card px box, image px box) for every OCR line that reads as an anchor."""
    h = card_h(template)
    found = []
    for i, anchor in enumerate(template["anchors"]):
        x0, y0, x1, y1 = anchor["box"]
        card = np.array([x0 * CARD_W, y0 * h, x1 * CARD_W, y1 * h])
        for b in boxes:
            if not b.virtual and _is_anchor(b.text, anchor["text"], normalize):
                found.append((i, card, np.array(b.box, np.float64)))
    return found


def _center(box: np.ndarray) -> np.ndarray:
    return np.array([(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])


def _residual(matrix: np.ndarray, src: np.ndarray, dst: np.ndarray, scale: float) -> np.ndarray:
    proj = cv2.perspectiveTransform(src.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    return np.linalg.norm(proj - dst, axis=1) / (scale * CARD_W)


def _from_anchors(boxes: list[OcrBox], template: dict, page_size, normalize: Callable[[str], str]) -> Registration | None:
    found = _matches(boxes, template, normalize)
    if len({i for i, _, _ in found}) < MIN_ANCHORS:
        return None
    # Line centers, not corners: OCR boxes vary in width (padding, a dropped character) and on a
    # still-tilted image their corners move with the tilt, while the center stays put.
    src = np.array([_center(c) for _, c, _ in found])
    dst = np.array([_center(d) for _, _, d in found])
    owner = np.array([i for i, _, _ in found])
    # rough scale from line heights, to express the RANSAC threshold in image pixels
    heights = [(d[3] - d[1]) / max(c[3] - c[1], 1) for _, c, d in found]
    scale_guess = float(np.median(heights))
    affine, inliers = cv2.estimateAffinePartial2D(
        src, dst, method=cv2.RANSAC, ransacReprojThreshold=MAX_RESIDUAL * CARD_W * scale_guess, maxIters=2000
    )
    if affine is None:
        return None
    keep = inliers.ravel().astype(bool)
    n_anchors = len(set(owner[keep]))
    if n_anchors < MIN_ANCHORS:
        return None
    matrix = np.vstack([affine, [0, 0, 1]])
    scale = math.hypot(affine[0, 0], affine[1, 0])
    rotation = math.degrees(math.atan2(affine[1, 0], affine[0, 0]))
    residual = float(_residual(matrix, src[keep], dst[keep], scale).mean())
    transform = "similarity"

    # A photo taken at an angle needs a perspective transform; only tried with enough anchors to pin it down.
    if n_anchors >= 4 and residual > 0.008:
        homography, mask = cv2.findHomography(src[keep], dst[keep], cv2.RANSAC, MAX_RESIDUAL * CARD_W * scale)
        if homography is not None:
            h_res = float(_residual(homography, src[keep], dst[keep], scale).mean())
            quad = cv2.perspectiveTransform(_card_corners(template).reshape(-1, 1, 2), homography).reshape(-1, 2)
            if h_res < 0.7 * residual and cv2.isContourConvex(quad.astype(np.float32)):
                matrix, residual, transform = homography, h_res, "homography"

    reg = Registration(matrix, "anchors", transform, n_anchors, residual, rotation, _card_fraction(matrix, template, page_size))
    return reg if _acceptable(reg) else None


def _from_crop(template: dict, page_size: tuple[int, int]) -> Registration | None:
    w, h = page_size
    if abs(w / h - template["aspect"]) > CROP_ASPECT_TOLERANCE:
        return None  # image was rotated after cropping (orientation / deskew): not the plain card any more
    matrix = np.diag([w / CARD_W, h / card_h(template), 1.0])
    return Registration(matrix, "crop", "scale", 0, None, 0.0, 1.0)


def _card_fraction(matrix: np.ndarray, template: dict, page_size) -> float | None:
    if not page_size:
        return None
    quad = cv2.perspectiveTransform(_card_corners(template).reshape(-1, 1, 2), matrix).reshape(-1, 2)
    width = (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2
    return float(width / page_size[0])


def _acceptable(reg: Registration) -> bool:
    if reg.residual is not None and reg.residual > MAX_RESIDUAL:
        return False
    if abs(reg.rotation_deg) > MAX_ROTATION_DEG:
        return False
    return reg.card_fraction is None or reg.card_fraction >= MIN_CARD_FRACTION
