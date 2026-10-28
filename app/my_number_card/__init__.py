"""My Number card (個人番号カード / マイナンバーカード, front side) parser: only the issuer and the expiry date."""

from .parser import parse_my_number_card

__all__ = ["parse_my_number_card"]
