"""
OTP queries for accounts.
"""

from apps.accounts.models import EmailOTP


def get_latest_pending_otp(user):
    """Return the newest unused OTP for a user, even if it has expired."""
    if not user:
        return None
    return EmailOTP.objects.filter(user=user, is_used=False).order_by("-created_at").first()


__all__ = ["get_latest_pending_otp"]
