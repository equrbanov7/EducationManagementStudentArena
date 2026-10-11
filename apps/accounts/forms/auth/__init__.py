"""accounts auth forms — geriyə-uyğun fasad paketi.

Sahib 2026-10-10: açıq qeydiyyat silindi — ``RegisterForm`` yoxdur.
"""

from ..otp import OTPPasswordResetConfirmForm  # noqa: F401
from .login import CustomLoginForm, CustomPasswordResetForm  # noqa: F401

__all__ = [
    "CustomLoginForm",
    "CustomPasswordResetForm",
    "OTPPasswordResetConfirmForm",
]
