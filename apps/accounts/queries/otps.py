"""
OTP queries for accounts.
"""

from apps.accounts.models import EmailOTP


def get_latest_pending_otp(user=None, *, email=None, purpose=None):
    """Return the newest unused OTP for a user/email, even if it has expired."""
    if not user and not email:
        return None
    return EmailOTP.pending_queryset(user=user, email=email, purpose=purpose).first()


__all__ = ["get_latest_pending_otp"]
