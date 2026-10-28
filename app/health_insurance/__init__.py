"""Japanese health insurance card (健康保険証 / 資格確認書, front side) parser: card type, insurer, date of issue."""

from .parser import parse_health_insurance

__all__ = ["parse_health_insurance"]
