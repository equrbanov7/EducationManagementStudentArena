"""
Authentication-related OTP services for accounts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import EmailOTP
from core.utils import (
    build_absolute_url,
    generate_otp,
    get_auth_otp_expiry_minutes,
    get_auth_otp_expiry_seconds,
    get_auth_otp_max_attempts,
    get_auth_otp_max_sends_per_hour,
    get_auth_otp_resend_cooldown_seconds,
)

from ..queries import get_latest_pending_otp
from .organization_requests import activate_verified_membership

logger = logging.getLogger(__name__)


class OTPServiceError(Exception):
    """Base OTP service exception."""


class OTPRateLimitError(OTPServiceError):
    """Raised when an email has reached the hourly OTP send limit."""

    def __init__(self, *, retry_after: int):
        super().__init__("OTP send limit reached.")
        self.retry_after = retry_after


class OTPResendCooldownError(OTPServiceError):
    """Raised when resend is attempted before the cooldown expires."""

    def __init__(self, *, retry_after: int):
        super().__init__("OTP resend cooldown active.")
        self.retry_after = retry_after


@dataclass(frozen=True)
class OTPVerificationResult:
    success: bool
    otp: EmailOTP | None = None
    reason: str = ""
    retry_after: int | None = None
    remaining_attempts: int | None = None


def _normalize_email(email: str) -> str:
    return EmailOTP.normalize_email(email)


def _otp_subject_for_purpose(purpose: str) -> str:
    return {
        EmailOTP.Purpose.SIGNUP: "EMSArena email təsdiqi",
        EmailOTP.Purpose.LOGIN: "EMSArena giriş OTP kodu",
        EmailOTP.Purpose.PASSWORD_RESET: "EMSArena şifrə sıfırlama OTP kodu",
        EmailOTP.Purpose.ADMIN_LOGIN: "EMSArena admin giriş OTP kodu",
    }.get(purpose, "EMSArena OTP kodu")


def _otp_headline_for_purpose(purpose: str) -> str:
    return {
        EmailOTP.Purpose.SIGNUP: "Email təsdiqi",
        EmailOTP.Purpose.LOGIN: "Giriş təsdiqi",
        EmailOTP.Purpose.PASSWORD_RESET: "Şifrə sıfırlama təsdiqi",
        EmailOTP.Purpose.ADMIN_LOGIN: "Admin giriş təsdiqi",
    }.get(purpose, "OTP təsdiqi")


def _otp_intro_for_purpose(purpose: str) -> str:
    return {
        EmailOTP.Purpose.SIGNUP: "hesabınızı aktivləşdirmək",
        EmailOTP.Purpose.LOGIN: "girişinizi təsdiqləmək",
        EmailOTP.Purpose.PASSWORD_RESET: "şifrəni sıfırlama əməliyyatını təsdiqləmək",
        EmailOTP.Purpose.ADMIN_LOGIN: "admin girişinizi təsdiqləmək",
    }.get(purpose, "əməliyyatı təsdiqləmək")


def _otp_cta_label_for_purpose(purpose: str) -> str:
    return {
        EmailOTP.Purpose.SIGNUP: "Emaili təsdiqlə",
        EmailOTP.Purpose.LOGIN: "Girişi təsdiqlə",
        EmailOTP.Purpose.PASSWORD_RESET: "Şifrəni sıfırla",
        EmailOTP.Purpose.ADMIN_LOGIN: "Admin girişi təsdiqlə",
    }.get(purpose, "OTP-ni təsdiqlə")


def _otp_template_prefix_for_purpose(purpose: str) -> str:
    if purpose == EmailOTP.Purpose.LOGIN:
        return "accounts/emails/login_otp_email"
    return "accounts/emails/verification_email"


def _build_verification_link(*, user, purpose: str, request=None) -> str:
    if purpose != EmailOTP.Purpose.SIGNUP or user is None:
        return ""

    from apps.accounts.views._helpers import signer

    verification_url = build_absolute_url(reverse("accounts:verify_email_link"), request=request)
    token = signer.sign(str(user.pk))
    return f"{verification_url}?token={token}"


def _build_email_context(*, user, email: str, purpose: str, code: str, request=None, expires_at=None) -> dict:
    recipient_name = ""
    if user is not None:
        recipient_name = getattr(user, "get_full_name", lambda: "")().strip() or getattr(user, "username", "")

    return {
        "user": user,
        "recipient_name": recipient_name or email,
        "email": email,
        "headline": _otp_headline_for_purpose(purpose),
        "otp_intro_action": _otp_intro_for_purpose(purpose),
        "cta_label": _otp_cta_label_for_purpose(purpose),
        "code": code,
        "verification_link": _build_verification_link(user=user, purpose=purpose, request=request),
        "otp_expiry_minutes": get_auth_otp_expiry_minutes(),
        "expires_at": expires_at,
        "purpose": purpose,
    }


def _send_otp_message(*, email: str, purpose: str, context: dict) -> None:
    template_prefix = _otp_template_prefix_for_purpose(purpose)
    text_body = render_to_string(f"{template_prefix}.txt", context)
    html_body = render_to_string(f"{template_prefix}.html", context)

    message = EmailMultiAlternatives(
        subject=_otp_subject_for_purpose(purpose),
        body=text_body,
        from_email=context.get("from_email"),
        to=[email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send()


def _count_recent_sends(*, email: str) -> tuple[int, EmailOTP | None]:
    window_start = timezone.now() - timedelta(hours=1)
    recent_qs = EmailOTP.objects.filter(email=email, created_at__gte=window_start).order_by("created_at")
    oldest_recent = recent_qs.first()
    return recent_qs.count(), oldest_recent


def issue_email_otp(
    user=None,
    *,
    email: str | None = None,
    purpose: str = EmailOTP.Purpose.SIGNUP,
    enforce_cooldown: bool = False,
):
    """Create a fresh OTP and invalidate older pending OTPs for the same purpose."""

    normalized_email = _normalize_email(email or getattr(user, "email", ""))
    if not normalized_email:
        raise ValueError("A valid email address is required to issue an OTP.")

    with transaction.atomic():
        pending_qs = EmailOTP.pending_queryset(user=user, email=normalized_email, purpose=purpose).select_for_update()
        latest_pending = pending_qs.first()
        now = timezone.now()

        if enforce_cooldown and latest_pending and not latest_pending.is_expired():
            elapsed = int((now - latest_pending.created_at).total_seconds())
            retry_after = get_auth_otp_resend_cooldown_seconds() - elapsed
            if retry_after > 0:
                raise OTPResendCooldownError(retry_after=retry_after)

        recent_count, oldest_recent = _count_recent_sends(email=normalized_email)
        if recent_count >= get_auth_otp_max_sends_per_hour():
            retry_after = 3600
            if oldest_recent is not None:
                retry_after = max(1, int((oldest_recent.created_at + timedelta(hours=1) - now).total_seconds()))
            raise OTPRateLimitError(retry_after=retry_after)

        pending_qs.update(is_used=True)

        code = generate_otp()
        expires_at = now + timedelta(seconds=get_auth_otp_expiry_seconds())
        otp_record = EmailOTP.objects.create(
            user=user,
            email=normalized_email,
            purpose=purpose,
            otp_hash=EmailOTP.build_otp_hash(email=normalized_email, otp=code, purpose=purpose),
            expires_at=expires_at,
        )

    return code, expires_at, otp_record


def send_otp_email(
    email: str,
    *,
    user=None,
    purpose: str = EmailOTP.Purpose.LOGIN,
    request=None,
    enforce_cooldown: bool = False,
):
    """Generate, persist, and send an OTP email."""

    code, expires_at, _otp_record = issue_email_otp(
        user,
        email=email,
        purpose=purpose,
        enforce_cooldown=enforce_cooldown,
    )
    normalized_email = _normalize_email(email or getattr(user, "email", ""))
    context = _build_email_context(
        user=user,
        email=normalized_email,
        purpose=purpose,
        code=code,
        request=request,
        expires_at=expires_at,
    )

    from django.conf import settings

    context["from_email"] = settings.DEFAULT_FROM_EMAIL

    try:
        _send_otp_message(email=normalized_email, purpose=purpose, context=context)
        logger.info("OTP email sent synchronously to %s for purpose %s", normalized_email, purpose)
        return code
    except Exception:
        logger.exception("OTP email delivery failed for %s", normalized_email)
        raise


def send_verification_otp(user, *, request=None, enforce_cooldown: bool = False):
    """Generate and send a signup verification OTP to the user's email."""

    return send_otp_email(
        user.email,
        user=user,
        purpose=EmailOTP.Purpose.SIGNUP,
        request=request,
        enforce_cooldown=enforce_cooldown,
    )


def send_login_otp(email, *, request=None, user=None, enforce_cooldown: bool = False):
    """Generate and send a login OTP to the provided email."""

    return send_otp_email(
        email,
        user=user,
        purpose=EmailOTP.Purpose.LOGIN,
        request=request,
        enforce_cooldown=enforce_cooldown,
    )


def get_otp_timer_context(user=None, *, email=None, purpose: str = EmailOTP.Purpose.SIGNUP):
    """Build OTP-expiry metadata for templates."""

    otp = get_latest_pending_otp(user, email=email, purpose=purpose)
    return {
        "otp_expires_at": getattr(otp, "expires_at", None),
        "otp_expiry_minutes": get_auth_otp_expiry_minutes(),
        "otp_expiry_seconds": get_auth_otp_expiry_seconds(),
    }


def verify_email_otp(
    *,
    email: str,
    code: str,
    user=None,
    purpose: str = EmailOTP.Purpose.SIGNUP,
) -> OTPVerificationResult:
    """Verify the provided OTP against the latest active record for an email/purpose."""

    normalized_email = _normalize_email(email or getattr(user, "email", ""))
    candidate = "".join(character for character in str(code or "").strip() if character.isdigit())
    if not normalized_email or len(candidate) != 6:
        return OTPVerificationResult(success=False, reason="invalid_format")

    with transaction.atomic():
        pending_qs = EmailOTP.pending_queryset(user=user, email=normalized_email, purpose=purpose).select_for_update()
        pending = list(pending_qs[:10])
        latest = pending[0] if pending else None
        if latest is None:
            return OTPVerificationResult(success=False, reason="missing")

        if latest.is_expired():
            latest.invalidate()
            return OTPVerificationResult(success=False, reason="expired")

        if int(latest.attempts_count or 0) >= get_auth_otp_max_attempts():
            latest.invalidate()
            return OTPVerificationResult(
                success=False,
                reason="max_attempts",
                remaining_attempts=0,
            )

        matched = next((otp for otp in pending if otp.matches_code(candidate)), None)
        if matched is None:
            latest.register_failed_attempt()
            return OTPVerificationResult(
                success=False,
                reason="invalid",
                remaining_attempts=latest.remaining_attempts,
            )

        pending_qs.exclude(pk=matched.pk).update(is_used=True)
        matched.mark_verified()
        return OTPVerificationResult(success=True, otp=matched, remaining_attempts=matched.remaining_attempts)


def verify_otp_code(user, code, *, purpose: str = EmailOTP.Purpose.SIGNUP):
    """Backward-compatible OTP verification wrapper used by existing form/views."""

    result = verify_email_otp(
        email=getattr(user, "email", ""),
        code=code,
        user=user,
        purpose=purpose,
    )
    return result.success, result.otp


def activate_user_account(user):
    """Activate the account and finalize any post-verification membership work."""

    user.is_active = True
    user.save(update_fields=["is_active"])
    return activate_verified_membership(user)


__all__ = [
    "OTPRateLimitError",
    "OTPResendCooldownError",
    "OTPVerificationResult",
    "activate_user_account",
    "get_otp_timer_context",
    "issue_email_otp",
    "send_login_otp",
    "send_otp_email",
    "send_verification_otp",
    "verify_email_otp",
    "verify_otp_code",
]
