"""Certificate of residence (住民票の写し) parser: only the issuer, the certification date and the address."""

from .parser import parse_resident_record

__all__ = ["parse_resident_record"]
