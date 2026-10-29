"""National Pension Handbook (国民年金手帳) / Basic Pension Number Notice (基礎年金番号通知書) parser:
only the basic pension number and the date of issue."""

from .parser import parse_pension

__all__ = ["parse_pension"]
