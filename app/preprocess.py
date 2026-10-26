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


def _card_quad(contour: np.ndarray, strict: bool) -> np.ndarray | None:
    approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
    if len(approx) != 4:
        return None
    rect = _order_corners(approx.reshape(4, 2).astype(np.float32))
    top, right = np.linalg.norm(rect[1] - rect[0]), np.linalg.norm(rect[2] - rect[1])
    bottom, left = np.linalg.norm(rect[2] - rect[3]), np.linalg.norm(rect[3] - rect[0])
    aspect = max(top, left) / max(min(top, left), 1)
    if abs(aspect - CARD_ASPECT) >= (0.25 if strict else 0.15):
        return None
    if not strict:  # loose edges also outline inner panels: also require a near-rectangle
        if max(top, bottom) / max(min(top, bottom), 1) > 1.15 or max(left, right) / max(min(left, right), 1) > 1.15:
            return None
    return rect


def _expand(rect: np.ndarray, ratio: float) -> np.ndarray:
    center = rect.mean(axis=0)
    return (center + (rect - center) * (1 + ratio)).astype(np.float32)


def find_card(img: np.ndarray) -> np.ndarray | None:
    """Return the 4 corners of the largest card-shaped quadrilateral, or None."""
    h, w = img.shape[:2]
    gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(gray, 50, 150), np.ones((3, 3), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        if cv2.contourArea(c) < 0.2 * w * h:
            break
        rect = _card_quad(c, strict=True)
        if rect is not None:
            return rect

    # Second pass for low-contrast edges (pale card, plastic sleeve, fingers over a corner): weaker
    # edges with gaps closed, convex hull to bridge occluded corners. The hull may cut a little into
    # the card, so the crop is widened slightly.
    edges = cv2.morphologyEx(cv2.Canny(gray, 20, 60), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    hulls = sorted((cv2.convexHull(c) for c in contours), key=cv2.contourArea, reverse=True)[:5]
    for hull in hulls:
        area = cv2.contourArea(hull)
        if area < 0.3 * w * h:
            break
        if area > 0.95 * w * h:  # the image border itself (card already cropped tight)
            continue
        rect = _card_quad(hull, strict=False)
        if rect is not None:
            rect = _expand(rect, 0.04)
            rect[:, 0] = rect[:, 0].clip(0, w - 1)
            rect[:, 1] = rect[:, 1].clip(0, h - 1)
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


def estimate_skew(polys: list[np.ndarray]) -> float:
    """Median tilt in degrees of the text lines' top edges (OCR quads, clockwise from top-left).

    Only wide boxes count: short ones (1-2 characters) give noisy angles.
    """
    angles = []
    for p in polys:
        p = np.asarray(p, dtype=np.float32).reshape(-1, 2)
        if len(p) != 4:
            continue
        dx, dy = p[1] - p[0]
        if np.hypot(dx, dy) > 2 * np.linalg.norm(p[3] - p[0]):
            angles.append(np.degrees(np.arctan2(dy, dx)))
    return float(np.median(angles)) if len(angles) >= 3 else 0.0


def rotate(img: np.ndarray, degrees: float) -> tuple[np.ndarray, np.ndarray]:
    """Rotate so a line tilted by `degrees` becomes horizontal; canvas grows to keep the corners.

    Returns the image and the 2x3 affine matrix to map points into it.
    """
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    new_w, new_h = int(h * sin + w * cos), int(h * cos + w * sin)
    m[0, 2] += new_w / 2 - w / 2
    m[1, 2] += new_h / 2 - h / 2
    out = cv2.warpAffine(img, m, (new_w, new_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return out, m


def encode_jpeg(img: np.ndarray, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("JPEG encode failed")
    return buf.tobytes()
