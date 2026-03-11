"""
Authentication-related services for accounts.
"""

from datetime import timedelta

from django.utils import timezone

from apps.blog.models import EmailOTP
from apps.blog.utils import generate_otp, send_verify_email
from core.utils import get_auth_otp_expiry_minutes, get_auth_otp_expiry_seconds

from ..queries import get_latest_pending_otp
from .organization_requests import activate_verified_student_membership


def send_verification_otp(user, *, request=None):
    """Generate and send an OTP code to the user's email."""
    code, expires_at = issue_email_otp(user)
    send_verify_email(user, code, request=request, expires_at=expires_at)
    return code


def issue_email_otp(user):
    """Create a fresh OTP for a user and invalidate older pending OTPs."""
    EmailOTP.objects.filter(user=user, is_used=False).update(is_used=True)

    code = generate_otp()
    expires_at = timezone.now() + timedelta(seconds=get_auth_otp_expiry_seconds())
    EmailOTP.objects.create(user=user, code=code, expires_at=expires_at)
    return code, expires_at


def get_otp_timer_context(user):
    """Build OTP-expiry metadata for templates."""
    otp = get_latest_pending_otp(user)
    return {
        "otp_expires_at": getattr(otp, "expires_at", None),
        "otp_expiry_minutes": get_auth_otp_expiry_minutes(),
        "otp_expiry_seconds": get_auth_otp_expiry_seconds(),
    }


def verify_otp_code(user, code):
    """Return whether the provided OTP code is valid for the user."""
    otp = EmailOTP.get_matching_otp(user=user, code=code)
    if not otp or otp.is_expired():
        return False, None
    return True, otp


def activate_user_account(user):
    """Activate the account and finalize any post-verification membership work."""
    user.is_active = True
    user.save(update_fields=["is_active"])
    return activate_verified_student_membership(user)


__all__ = [
    "activate_user_account",
    "get_otp_timer_context",
    "issue_email_otp",
    "send_verification_otp",
    "verify_otp_code",
]
