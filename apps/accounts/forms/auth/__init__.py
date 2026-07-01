"""accounts auth forms — geriyə-uyğun fasad paketi."""

from ..otp import OTPPasswordResetConfirmForm  # noqa: F401
from .login import CustomLoginForm, CustomPasswordResetForm  # noqa: F401
from .register import RegisterForm  # noqa: F401

__all__ = [
    "CustomLoginForm",
    "CustomPasswordResetForm",
    "OTPPasswordResetConfirmForm",
    "RegisterForm",
]
