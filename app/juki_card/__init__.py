"""Basic Resident Register Card (住民基本台帳カード, photo type, front side) parser: only the issuer and the expiry date."""

from .parser import parse_juki_card

__all__ = ["parse_juki_card"]
