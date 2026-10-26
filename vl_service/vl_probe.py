"""Dev only: print PaddleOCR-VL's raw output format and speed for one image, in both modes.

Usage (from vl_service/, with its venv): .venv/bin/python vl_probe.py <image> [pipeline_version]
"""

import json
import sys
import time

from paddleocr import PaddleOCRVL

KEYS = ("label", "bbox", "content", "block_label", "block_bbox", "block_content")


def main(image: str, version: str) -> None:
    t = time.perf_counter()
    vl = PaddleOCRVL(pipeline_version=version, use_doc_orientation_classify=False, use_doc_unwarping=False)
    print("init_s", round(time.perf_counter() - t, 1), flush=True)
    for mode in ("layout", "whole"):
        t = time.perf_counter()
        kwargs = {} if mode == "layout" else {"use_layout_detection": False, "prompt_label": "ocr"}
        res = list(vl.predict(image, **kwargs))[0]
        print("=====", mode, "predict_s", round(time.perf_counter() - t, 1))
        print("keys", list(res.keys()))
        for b in res["parsing_res_list"]:
            d = b if isinstance(b, dict) else {k: getattr(b, k, None) for k in ("label", "bbox", "content")}
            shown = {k: (str(v)[:200] if k.endswith("content") else v) for k, v in d.items() if k in KEYS}
            print(json.dumps(shown, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "v1.5")
