"""Whether the OCR result as a whole can be trusted."""

from __future__ import annotations

from .layout import Document


def assess_quality(doc: Document, labels_found: int, labels_expected: int, label_kind: str) -> dict:
    """Flag images where OCR clearly struggled, so results are not trusted silently.
    `label_kind` names the labels counted in the message (e.g. "tiếng Nhật")."""
    reasons = []
    mean = doc.mean_score
    low_share = sum(s < 0.8 for s in doc.ocr_scores) / len(doc.ocr_scores) if doc.ocr_scores else 1.0
    if mean is None:
        reasons.append("Không đọc được chữ nào trên ảnh.")
    elif mean < 0.9:
        reasons.append(f"Độ tin cậy OCR trung bình thấp ({mean:.2f}).")
    if doc.ocr_scores and low_share > 0.2:
        reasons.append(f"{low_share:.0%} dòng chữ có độ tin cậy dưới 0.8.")
    if labels_found < labels_expected * 0.6:
        reasons.append(f"Chỉ nhận ra {labels_found}/{labels_expected} nhãn {label_kind}.")
    return {
        "level": "low" if reasons else "ok",
        "reasons": reasons,
        "advice": "Nên chụp/scan lại rõ hơn (chiều ngang thẻ ≥ 1500px, không lóa, không watermark) hoặc nhập tay các trường cần kiểm tra."
        if reasons else None,
    }
