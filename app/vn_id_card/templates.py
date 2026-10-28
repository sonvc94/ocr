"""Card templates per design (data/templates.json): "2024" measured on the official specimen image, "cccd_2021" on a
real card photo. Format: card_core/templates.py."""

from __future__ import annotations

from pathlib import Path

from ..card_core.templates import load_templates

TEMPLATES = load_templates(Path(__file__).parent / "data" / "templates.json")
