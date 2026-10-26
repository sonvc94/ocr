"""Probe PaddleOCR-VL output format and speed on one image (dev only)."""
import json, sys, time
from paddleocr import PaddleOCRVL

t = time.perf_counter()
vl = PaddleOCRVL(pipeline_version=sys.argv[2], use_doc_orientation_classify=False, use_doc_unwarping=False)
print("init_s", round(time.perf_counter() - t, 1), flush=True)
for mode in ("layout", "whole"):
    t = time.perf_counter()
    kw = {} if mode == "layout" else {"use_layout_detection": False, "prompt_label": "ocr"}
    res = list(vl.predict(sys.argv[1], **kw))[0]
    print("=====", mode, "predict_s", round(time.perf_counter() - t, 1))
    print("keys", list(res.keys()))
    for b in res["parsing_res_list"]:
        d = b if isinstance(b, dict) else {k: getattr(b, k, None) for k in ("label", "bbox", "content")}
        print(json.dumps({k: (str(v)[:200] if k == "content" else v) for k, v in d.items() if k in ("label", "bbox", "content", "block_label", "block_bbox", "block_content")}, ensure_ascii=False, default=str))
