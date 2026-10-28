"""Dev-only: compare PaddleOCR det/rec model pairs on Vietnamese card images (text read + time).

Usage: python -m scripts.bench_vi_rec samples/vn/synthetic_0.jpg ... > samples/results/vn_model_bench.txt
"""

from __future__ import annotations

import sys
import time

import cv2
from paddleocr import PaddleOCR

from app.preprocess import normalize_card

CANDIDATES = [
    ("PP-OCRv5_server_det", "PP-OCRv5_server_rec"),
    ("PP-OCRv5_server_det", "latin_PP-OCRv5_mobile_rec"),
    ("PP-OCRv5_server_det", "PP-OCRv6_medium_rec"),
    ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"),
]

if __name__ == "__main__":
    images = [(p, normalize_card(cv2.imread(p))[0]) for p in sys.argv[1:]]
    for det, rec in CANDIDATES:
        ocr = PaddleOCR(
            text_detection_model_name=det, text_recognition_model_name=rec, use_doc_orientation_classify=True,
            use_doc_unwarping=False, use_textline_orientation=False,
        )
        print(f"=== {det} + {rec}")
        for path, img in images:
            ocr.predict(img)  # warm-up
            t = time.perf_counter()
            res = list(ocr.predict(img))[0]
            ms = (time.perf_counter() - t) * 1000
            print(f"--- {path} ({ms:.0f} ms)")
            for text, score in zip(res["rec_texts"], res["rec_scores"]):
                print(f"  {score:.3f}  {text}")
        sys.stdout.flush()
