"""Japanese driver's license (運転免許証) and driving history certificate (運転経歴証明書), front side:
only the license number and the date of issue."""

from .parser import parse_driver_license, parse_driving_history

__all__ = ["parse_driver_license", "parse_driving_history"]
