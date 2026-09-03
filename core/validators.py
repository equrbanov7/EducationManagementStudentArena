"""
Core validators for EMS Arena project.
Custom validation functions for forms and models.
"""

import re
import unicodedata

from django.core.exceptions import ValidationError

#: Azərbaycan şəxsiyyət vəsiqəsi FİN kodunun dəqiq uzunluğu.
FIN_LENGTH = 7
#: FİN formatı: tam 7 simvol, yalnız böyük latın hərfi və rəqəm.
FIN_PATTERN = re.compile(r"[A-Z0-9]{7}\Z")


def validate_positive(value):
    """
    Validate that a value is positive.
    """
    if value < 0:
        raise ValidationError(f"{value} is not a positive number")


def validate_file_size(value, max_size_mb=10):
    """
    Validate file size.

    Args:
        value: File object
        max_size_mb: Maximum file size in megabytes
    """
    filesize = value.size
    if filesize > max_size_mb * 1024 * 1024:
        raise ValidationError(f"File size cannot exceed {max_size_mb}MB")


def normalize_fin(value: object) -> str:
    """NFKC → strip → remove inner whitespace → upper. Returns '' for empty/None."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    return "".join(text.split()).upper()


def validate_fin(value):
    """Model/form validator: exactly 7 chars of [A-Z0-9] (AZ FİN format)."""
    if value in (None, ""):
        return
    if type(value) is not str or not FIN_PATTERN.fullmatch(value):
        raise ValidationError("FİN kodu 7 simvolluq [A-Z0-9] formatında olmalıdır.")
