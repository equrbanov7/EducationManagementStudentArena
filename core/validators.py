"""
Core validators for EMS Arena project.
Custom validation functions for forms and models.
"""

from django.core.exceptions import ValidationError


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
