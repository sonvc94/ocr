"""Card detection and deskew on synthetic images (OpenCV only, no Paddle needed)."""

import cv2
import numpy as np

from app.preprocess import CARD_ASPECT, estimate_skew, find_card, normalize_card, rotate


def card_photo(degrees: float, card_gray: int, bg_gray: int) -> tuple[np.ndarray, np.ndarray]:
    """A flat card tilted on a background, with dark text bars; returns the image and true corners."""
    img = np.full((1100, 1500, 3), bg_gray, np.uint8)
    w, h = 1000, int(1000 / CARD_ASPECT)
    corners = cv2.boxPoints(((750, 550), (w, h), degrees)).astype(np.float32)
    cv2.fillPoly(img, [corners.astype(np.int32)], (card_gray,) * 3)
    m = cv2.getRotationMatrix2D((750, 550), -degrees, 1.0)  # same tilt for the text bars
    for i in range(6):
        bar = np.array([[450, 330 + i * 70], [900, 330 + i * 70], [900, 360 + i * 70], [450, 360 + i * 70]], np.float32)
        cv2.fillPoly(img, [(bar @ m[:, :2].T + m[:, 2]).astype(np.int32)], (40, 40, 40))
    return img, corners


def test_find_card_low_contrast_tilted():
    # Pale card on a near-identical background: too faint for the first (Canny 50/150) pass
    img, corners = card_photo(-7, card_gray=222, bg_gray=195)
    cv2.circle(img, tuple(int(v) for v in corners[np.argmax(corners[:, 1])]), 60, (170, 150, 140), -1)  # finger
    rect = find_card(img)
    assert rect is not None
    # The crop holds the whole card (it is widened a little on purpose) without much background
    for c in corners:
        assert cv2.pointPolygonTest(rect.reshape(-1, 1, 2), tuple(float(v) for v in c), True) > -5
    assert cv2.contourArea(rect) < 1.25 * cv2.contourArea(corners)


def test_find_card_small_on_wood_grain():
    # Pale cyan card filling ~18% of a portrait phone photo on orange wood grain: the grain breaks the
    # card outline at full resolution and touches it (log 6337de321938, fd35bf5e2740, 27/10/2026)
    rng = np.random.default_rng(0)
    h, w = 2000, 1125
    xs = np.arange(w)[None, :] + 25 * np.sin(np.arange(h)[:, None] / 90)
    grain = (np.sin(xs / 6) * 25 + rng.normal(0, 12, (h, w))).astype(np.float32)
    img = np.clip(np.stack([60 + grain, 120 + grain, 180 + grain], axis=2), 0, 255).astype(np.uint8)
    cw = 780
    corners = cv2.boxPoints(((560, 900), (cw, cw / CARD_ASPECT), -2)).astype(np.float32)
    cv2.fillPoly(img, [corners.astype(np.int32)], (215, 225, 170))
    for i in range(6):
        cv2.rectangle(img, (420, 760 + i * 50), (850, 780 + i * 50), (40, 40, 40), -1)
    rect = find_card(img)
    assert rect is not None
    for c in corners:
        assert cv2.pointPolygonTest(rect.reshape(-1, 1, 2), tuple(float(v) for v in c), True) > -15
    assert cv2.contourArea(rect) < 1.15 * cv2.contourArea(corners)


def test_tight_crop_is_left_alone():
    # A card that already fills the image (web scan) has no edge to find: no inner panel must be cropped
    img, _ = card_photo(0, card_gray=230, bg_gray=230)
    out, cropped = normalize_card(img[200:900, 200:1300])
    assert not cropped


def test_estimate_skew_and_rotate():
    quads = []
    m = cv2.getRotationMatrix2D((500, 300), 6, 1.0)  # text rising to the right by 6°
    for i in range(5):
        q = np.array([[100, 100 + i * 60], [700, 100 + i * 60], [700, 130 + i * 60], [100, 130 + i * 60]], np.float32)
        quads.append(q @ m[:, :2].T + m[:, 2])
    quads.append(np.array([[0, 0], [20, 15], [10, 35], [-10, 20]], np.float32))  # short box: ignored
    skew = estimate_skew(quads)
    assert abs(skew + 6) < 0.1

    img = np.zeros((600, 1000, 3), np.uint8)
    rotated, m2 = rotate(img, skew)
    q = quads[0] @ m2[:, :2].T + m2[:, 2]
    assert abs(q[0, 1] - q[1, 1]) < 1  # top edge is horizontal again
    assert (q >= 0).all() and (q[:, 0] < rotated.shape[1]).all() and (q[:, 1] < rotated.shape[0]).all()


def test_estimate_skew_needs_enough_lines():
    assert estimate_skew([np.array([[0, 0], [300, 30], [297, 60], [-3, 30]], np.float32)]) == 0.0
