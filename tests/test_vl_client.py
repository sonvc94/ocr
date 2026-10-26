"""Conversion of PaddleOCR-VL blocks into parser input (no VL service needed)."""

import http.client
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from app import config
from app.ocr import vl_client
from app.ocr.vl_client import blocks_to_boxes
from app.residence_card import parse_residence_card


def test_block_lines_split_inside_bbox():
    boxes = blocks_to_boxes([{"label": "text", "bbox": [10, 100, 510, 160], "content": "氏名\nNGUYEN VAN AN\n"}], (1600, 1009))
    assert [b.text for b in boxes] == ["氏名", "NGUYEN VAN AN"]
    assert boxes[0].box == (10, 100, 510, 130)
    assert boxes[1].box == (10, 130, 510, 160)


def test_whole_image_text_is_parsed():
    content = "在留カード 番号 AB12345678CD\n氏名 NGUYEN VAN AN\n生年月日 1995年04月12日 性別 男 M. 国籍・地域 ベトナム"
    boxes = blocks_to_boxes([{"label": "ocr", "bbox": None, "content": content}], (1600, 1009))
    assert len(boxes) == 3 and boxes[0].cy < boxes[1].cy < boxes[2].cy
    fields = parse_residence_card(boxes)["fields"]
    assert fields["card_number"]["value"] == "AB12345678CD"
    assert fields["name"]["value"] == "NGUYEN VAN AN"
    assert fields["date_of_birth"]["value"] == "1995-04-12"
    assert fields["nationality"]["value"] == "ベトナム"


def test_service_dropping_connection_is_unavailable(monkeypatch):
    class Hangup(BaseHTTPRequestHandler):
        def do_POST(self):
            self.close_connection = True  # reply nothing, like a VL service crashing mid-request

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Hangup)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(config, "VL_URL", f"http://127.0.0.1:{server.server_port}")
    try:
        with pytest.raises(vl_client.VlUnavailable) as exc_info:
            vl_client.run_vl(np.zeros((10, 10, 3), dtype=np.uint8))
        assert isinstance(exc_info.value.__cause__, http.client.RemoteDisconnected)
    finally:
        server.shutdown()
