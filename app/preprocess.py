"""Image loading and card normalization: EXIF rotation, card crop + perspective correction."""

from __future__ import annotations

import io

import cv2
import numpy as np
from PIL import Image, ImageOps

# ID-1 card (85.60 x 53.98 mm).
CARD_ASPECT = 85.60 / 53.98
CARD_WIDTH = 1600
MAX_SIDE = 2000
# Small images (e.g. a 500px-wide card cut from a web page) lose kana and thin strokes;
# upscaling before detection recovers part of them.
MIN_SIDE = 1200
UPSCALE_TO = 1600


def load_image(data: bytes) -> tuple[np.ndarray, tuple[int, int]]:
    """Decode upload bytes to a BGR array, honoring the phone's EXIF orientation.

    Also returns the original (width, height), which tells whether a bad result came from a tiny image.
    """
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    original_size = img.size
    arr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    h, w = arr.shape[:2]
    if max(h, w) > MAX_SIDE:
        scale = MAX_SIDE / max(h, w)
        arr = cv2.resize(arr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    elif max(h, w) < MIN_SIDE:
        scale = UPSCALE_TO / max(h, w)
        arr = cv2.resize(arr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    return arr, original_size


def _order_corners(pts: np.ndarray) -> np.ndarray:
    s, d = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.array([pts[s.argmin()], pts[d.argmin()], pts[s.argmax()], pts[d.argmax()]], dtype=np.float32)


def find_card(img: np.ndarray) -> np.ndarray | None:
    """Return the 4 corners of the largest card-shaped quadrilateral, or None."""
    h, w = img.shape[:2]
    gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(gray, 50, 150), np.ones((3, 3), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        area = cv2.contourArea(c)
        if area < 0.2 * w * h:
            break
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) != 4:
            continue
        rect = _order_corners(approx.reshape(4, 2).astype(np.float32))
        width = np.linalg.norm(rect[1] - rect[0])
        height = np.linalg.norm(rect[3] - rect[0])
        aspect = max(width, height) / max(min(width, height), 1)
        if abs(aspect - CARD_ASPECT) < 0.25:
            return rect
    return None


def normalize_card(img: np.ndarray) -> tuple[np.ndarray, bool]:
    """Crop and flatten the card if it can be located; otherwise return the image unchanged."""
    rect = find_card(img)
    if rect is None:
        return img, False
    width = np.linalg.norm(rect[1] - rect[0])
    height = np.linalg.norm(rect[3] - rect[0])
    if height > width:  # card photographed in portrait: rotate corners so the long side is horizontal
        rect = np.roll(rect, -1, axis=0)
    out_w, out_h = CARD_WIDTH, int(CARD_WIDTH / CARD_ASPECT)
    dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(img, matrix, (out_w, out_h)), True


def encode_jpeg(img: np.ndarray, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("JPEG encode failed")
    return buf.tobytes()
