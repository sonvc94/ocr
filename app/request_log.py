"""Per-request logging: one summary line without personal data, plus opt-in full results and images (PII)."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config

logger = logging.getLogger("uvicorn.error")
_log_lock = threading.Lock()


def log_result(request_id: str, filename: str | None, result: dict) -> None:
    fields = result["fields"]
    missing = [k for k, f in fields.items() if f["value"] is None]
    review = [k for k, f in fields.items() if f["needs_review"] and f["value"] is not None]
    logger.info(
        "extract id=%s doc=%s model=%s file=%s size=%s quality=%s found=%d/%d missing=%s review=%s anchored=%s detect=%s timing=%s",
        request_id, result["document_type"], result["ocr"]["model"], filename, result["ocr"]["original_size"], result["quality"]["level"],
        len(fields) - len(missing), len(fields), missing, review,
        result["labels_from_english_anchor"], _detection_summary(result.get("document_detection")), result["timing_ms"],
    )
    if not config.LOG_RESPONSES:
        return
    entry = {"id": request_id, "time": datetime.now(timezone.utc).isoformat(), "filename": filename}
    entry |= {k: v for k, v in result.items() if k != "processed_image"}
    config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _log_lock, config.LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _detection_summary(det: dict | None) -> str | None:
    """document=auto only: how the document was chosen, with the scores when it was not certain."""
    if det is None:
        return None
    if det["detected"] is None:
        how = "none"
    else:
        how = "guessed" if det["guessed"] else "confident" if det["confident"] else "uncertain"
    return how if how == "confident" else f"{how} {det['guess_scores'] or det['scores']}"


def save_image(request_id: str, kind: str, data: bytes, suffix: str) -> None:
    """Write logs/images/<request_id>_<kind><suffix> when DEBUG_SAVE_IMAGES=1."""
    if not config.DEBUG_SAVE_IMAGES:
        return
    config.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    (config.IMAGE_DIR / f"{request_id}_{kind}{suffix}").write_bytes(data)


def upload_suffix(filename: str | None) -> str:
    return Path(filename or "").suffix.lower() or ".img"
