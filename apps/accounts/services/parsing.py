"""
Parsing helpers for accounts services.
"""

from decimal import Decimal, InvalidOperation


def parse_decimal_score(value, *, default=None):
    """Parse a score-like value to ``Decimal``."""
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value

    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return default


__all__ = ["parse_decimal_score"]
