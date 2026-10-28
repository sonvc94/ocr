"""Vietnamese identity card (thẻ căn cước 2024, chip CCCD 2021; front side) parser: OCR lines in, JSON-ready fields out."""

from .parser import MODES, parse_vn_id_card

__all__ = ["MODES", "parse_vn_id_card"]
