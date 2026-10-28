"""Residence card (在留カード, front side) parser: OCR lines in, JSON-ready fields out."""

from ..card_core.layout import group_rows
from .parser import MODES, parse_residence_card

__all__ = ["MODES", "group_rows", "parse_residence_card"]
