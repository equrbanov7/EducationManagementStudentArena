"""
apps/accounts/forms/__init__.py

Public API for the accounts forms package.
Re-exports all form classes so that existing imports remain stable:
  ``from ..forms import CustomLoginForm``            ← still works
  ``from apps.accounts.forms import OTPPasswordResetConfirmForm``  ← still works
"""

from .auth import (
    CustomLoginForm,
    CustomPasswordResetForm,
    OTPPasswordResetConfirmForm,
)
from .otp import OTPPasswordResetCodeForm, OTPPasswordResetConfirmForm  # noqa: F811 – canonical location
from .profile import CustomPasswordChangeForm

__all__ = [
    "CustomLoginForm",
    "CustomPasswordChangeForm",
    "CustomPasswordResetForm",
    "OTPPasswordResetCodeForm",
    "OTPPasswordResetConfirmForm",
]
