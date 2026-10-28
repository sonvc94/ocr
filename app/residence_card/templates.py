"""Residence card templates (data/templates.json), measured on the ISA specimen images. Format: card_core/templates.py."""

from __future__ import annotations

from pathlib import Path

from ..card_core.templates import load_templates

TEMPLATES = load_templates(Path(__file__).parent / "data" / "templates.json")
