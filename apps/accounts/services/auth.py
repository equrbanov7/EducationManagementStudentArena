"""
Authentication-related services for accounts.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.accounts.models import EmailOTP
from apps.blog.utils import generate_otp, send_verify_email
from core.utils import build_absolute_url, get_auth_otp_expiry_minutes, get_auth_otp_expiry_seconds

from ..queries import get_latest_pending_otp
from .organization_requests import activate_verified_membership

logger = logging.getLogger(__name__)


def send_verification_otp(user, *, request=None):
    """Generate and send an OTP code to the user's email.

    Sends synchronously via ``send_verify_email`` so that delivery failures
    raise immediately and can be caught by the caller. If the synchronous
    send fails, we fall back to a best-effort async Celery send so that
    transient SMTP hiccups don't silently drop the message.

    Raises the underlying exception from the email backend (e.g.
    ``smtplib.SMTPException``, ``ConnectionError``, or any
    ``django.core.mail`` transport error) when **both** the synchronous
    and async paths fail, letting the caller roll back any in-progress
    transaction (e.g. user creation).
    """
    code, expires_at = issue_email_otp(user)

    # Primary path: synchronous send so failures are surfaced immediately.
    try:
        send_verify_email(user, code, request=request, expires_at=expires_at)
        logger.info("Verification OTP email sent synchronously to user %s", user.pk)
        return code
    except Exception as exc:
        logger.warning(
            "Synchronous OTP email send failed for user %s (%s); attempting async fallback",
            user.pk,
            exc,
        )

    # Fallback path: enqueue via Celery.  We still return the code so the
    # session/redirect can proceed; the background task will retry on failure.
    try:
        from django.core.signing import TimestampSigner
        from django.urls import reverse

        from core.email_tasks import send_verification_otp_email

        verification_url = build_absolute_url(reverse("accounts:verify_email_link"), request=request)
        signer = TimestampSigner()
        token = signer.sign(str(user.pk))
        verification_link = f"{verification_url}?token={token}"

        send_verification_otp_email.delay(
            user_pk=user.pk,
            code=code,
            expires_at=expires_at.isoformat() if expires_at else None,
            verification_link=verification_link,
            otp_expiry_minutes=get_auth_otp_expiry_minutes(),
        )
        logger.info("Verification OTP email queued (async) for user %s", user.pk)
        return code
    except Exception as exc:
        logger.exception(
            "Both synchronous and async OTP email delivery failed for user %s", user.pk
        )
        raise


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
    return activate_verified_membership(user)


__all__ = [
    "activate_user_account",
    "get_otp_timer_context",
    "issue_email_otp",
    "send_verification_otp",
    "verify_otp_code",
]
