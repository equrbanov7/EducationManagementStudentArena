"""
Authentication-related OTP services for accounts.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import connection, transaction
from django.template.loader import render_to_string
from django.utils import timezone, translation
from django.utils.translation import pgettext_lazy

from apps.accounts.models import EmailOTP
from core.mailing import sender_for, system_reply_to
from core.utils import (
    generate_otp,
    get_auth_otp_expiry_minutes,
    get_auth_otp_expiry_seconds,
    get_auth_otp_max_attempts,
    get_auth_otp_max_sends_per_hour,
    get_auth_otp_resend_cooldown_seconds,
)

from ..identity import (
    StagedAccountAccessError,
    assert_account_access_allowed,
    staged_user_for_email,
)
from ..queries import get_latest_pending_otp
from .organization_requests import activate_verified_membership

logger = logging.getLogger(__name__)


class OTPServiceError(Exception):
    """Base OTP service exception."""


class OTPRateLimitError(OTPServiceError):
    """Raised when an email has reached the hourly OTP send limit."""

    def __init__(self, retry_after: int):
        super().__init__("OTP send limit reached.")
        self.retry_after = retry_after


class OTPResendCooldownError(OTPServiceError):
    """Raised when resend is attempted before the cooldown expires."""

    def __init__(self, retry_after: int):
        super().__init__("OTP resend cooldown active.")
        self.retry_after = retry_after


@dataclass(frozen=True)
class OTPVerificationResult:
    """``reason``: ``invalid`` (səhv kod), ``expired``, ``superseded`` (yenisi ilə əvəzlənib),
    ``already_used``, ``max_attempts``, ``missing``, ``invalid_format``, ``access_denied``."""

    success: bool
    otp: EmailOTP | None = None
    reason: str = ""
    retry_after: int | None = None
    remaining_attempts: int | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True)
class OTPSendResult:
    """``request_email_otp`` nəticəsi: ``reused`` → yeni kod/məktub YOXDUR, əvvəlki kod qüvvədədir."""

    reused: bool
    expires_at: datetime
    resend_available_in: int


#: Sahib 2026-10-21 («2 dəfə OTP göndərəndə problem olur»): ard-arda göndərilmiş SON N kod (hər biri öz
#: müddətinə qədər) qəbul olunur — istifadəçi hansı məktubu açsa, o kod işləyir. Səhv cəhd sayğacı ən
#: son kodda gedir və o bağlananda HAMISI bağlanır (təxmin büdcəsi artmır).
OTP_ACCEPTED_RECENT_CODES = 3

#: Köhnə kodun səbəbini (vaxtı keçib / istifadə olunub / əvəzlənib) tanımaq üçün baxılan pəncərə.
_STALE_LOOKBACK = timedelta(hours=24)


def _normalize_email(email: str) -> str:
    return EmailOTP.normalize_email(email)


#: E-poçt mətnləri — hamısı tərcümə kataloqundan (sahib 2026-09-21: «məktub iki
#: dildə qarışıq gəlir»). Əvvəllər mövzu/başlıq/«… üçün» ifadəsi Python-da sabit
#: azərbaycanca idi, şablonun qalan sətirləri isə aktiv dilə (EN) tərcümə olunurdu.
_MAIL_CTX = "accounts.email_otp"


def _otp_subject_for_purpose(purpose: str) -> str:
    brand = getattr(settings, "SITE_BRAND_NAME", "") or "Qərbi Kaspi Universiteti"
    template = {
        EmailOTP.Purpose.SIGNUP: pgettext_lazy(_MAIL_CTX, "%(brand)s email təsdiqi"),
        EmailOTP.Purpose.LOGIN: pgettext_lazy(_MAIL_CTX, "%(brand)s giriş OTP kodu"),
        EmailOTP.Purpose.PASSWORD_RESET: pgettext_lazy(_MAIL_CTX, "%(brand)s şifrə sıfırlama OTP kodu"),
        EmailOTP.Purpose.ADMIN_LOGIN: pgettext_lazy(_MAIL_CTX, "%(brand)s admin giriş OTP kodu"),
    }.get(purpose, pgettext_lazy(_MAIL_CTX, "%(brand)s OTP kodu"))
    return str(template) % {"brand": brand}


def _otp_headline_for_purpose(purpose: str):
    return {
        EmailOTP.Purpose.SIGNUP: pgettext_lazy(_MAIL_CTX, "Email təsdiqi"),
        EmailOTP.Purpose.LOGIN: pgettext_lazy(_MAIL_CTX, "Giriş təsdiqi"),
        EmailOTP.Purpose.PASSWORD_RESET: pgettext_lazy(_MAIL_CTX, "Şifrə sıfırlama təsdiqi"),
        EmailOTP.Purpose.ADMIN_LOGIN: pgettext_lazy(_MAIL_CTX, "Admin giriş təsdiqi"),
    }.get(purpose, pgettext_lazy(_MAIL_CTX, "OTP təsdiqi"))


def _otp_intro_for_purpose(purpose: str):
    return {
        EmailOTP.Purpose.SIGNUP: pgettext_lazy(_MAIL_CTX, "hesabınızı aktivləşdirmək"),
        EmailOTP.Purpose.LOGIN: pgettext_lazy(_MAIL_CTX, "girişinizi təsdiqləmək"),
        EmailOTP.Purpose.PASSWORD_RESET: pgettext_lazy(_MAIL_CTX, "şifrəni sıfırlama əməliyyatını təsdiqləmək"),
        EmailOTP.Purpose.ADMIN_LOGIN: pgettext_lazy(_MAIL_CTX, "admin girişinizi təsdiqləmək"),
    }.get(purpose, pgettext_lazy(_MAIL_CTX, "əməliyyatı təsdiqləmək"))


def _otp_cta_label_for_purpose(purpose: str):
    return {
        EmailOTP.Purpose.SIGNUP: pgettext_lazy(_MAIL_CTX, "Emaili təsdiqlə"),
        EmailOTP.Purpose.LOGIN: pgettext_lazy(_MAIL_CTX, "Girişi təsdiqlə"),
        EmailOTP.Purpose.PASSWORD_RESET: pgettext_lazy(_MAIL_CTX, "Şifrəni sıfırla"),
        EmailOTP.Purpose.ADMIN_LOGIN: pgettext_lazy(_MAIL_CTX, "Admin girişi təsdiqlə"),
    }.get(purpose, pgettext_lazy(_MAIL_CTX, "OTP-ni təsdiqlə"))


def _otp_template_prefix_for_purpose(purpose: str) -> str:
    if purpose == EmailOTP.Purpose.LOGIN:
        return "accounts/emails/login_otp_email"
    return "accounts/emails/verification_email"


def _build_email_context(*, user, email: str, purpose: str, code: str, request=None, expires_at=None) -> dict:
    recipient_name = ""
    if user is not None:
        recipient_name = getattr(user, "get_full_name", lambda: "")().strip() or getattr(user, "username", "")

    return {
        # White-label brand for the email chrome; emails render without the
        # request context processors so it must be passed explicitly.
        "brand": getattr(settings, "SITE_BRAND_NAME", "") or "Qərbi Kaspi Universiteti",
        "user": user,
        "recipient_name": recipient_name or email,
        "email": email,
        "headline": _otp_headline_for_purpose(purpose),
        "otp_intro_action": _otp_intro_for_purpose(purpose),
        "cta_label": _otp_cta_label_for_purpose(purpose),
        "code": code,
        # Sahib 2026-10-10: açıq qeydiyyat (və `accounts/verify-email/` link-aktivləşdirməsi)
        # silindi — məktubda yalnız kod var; şablon boş linki göstərmir.
        "verification_link": "",
        "otp_expiry_minutes": get_auth_otp_expiry_minutes(),
        "expires_at": expires_at,
        "purpose": purpose,
        # Məktubun dili — sorğunun aktiv dili (bütün məktub BİR dildə render olunur).
        "language": translation.get_language() or settings.LANGUAGE_CODE,
    }


def _send_otp_message(*, email: str, purpose: str, context: dict) -> None:
    template_prefix = _otp_template_prefix_for_purpose(purpose)
    # Mövzu, başlıq və gövdə EYNİ dildə: fon ipində/başqa aktiv dildə çağırılsa
    # belə context-dəki dil qalib gəlir (sahib 2026-09-21).
    with translation.override(context.get("language") or settings.LANGUAGE_CODE):
        subject = _otp_subject_for_purpose(purpose)
        text_body = render_to_string(f"{template_prefix}.txt", context)
        html_body = render_to_string(f"{template_prefix}.html", context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=context.get("from_email"),
        to=[email],
        reply_to=system_reply_to(),
    )
    message.attach_alternative(html_body, "text/html")
    message.send()


def _count_recent_sends(*, email: str) -> tuple[int, EmailOTP | None]:
    window_start = timezone.now() - timedelta(hours=1)
    recent_qs = EmailOTP.objects.filter(email=email, created_at__gte=window_start).order_by("created_at")
    oldest_recent = recent_qs.first()
    return recent_qs.count(), oldest_recent


def _lock_otp_scope(*, email: str, purpose: str) -> None:
    """Eyni (məqsəd, e-poçt) üçün paralel kod buraxılışını ardıcıllaşdır (tranzaksiya sonunadək).

    ``select_for_update`` yalnız MÖVCUD sətirləri kilidləyir — hələ kod yoxdursa iki paralel sorğu
    (ikiqat klik) hər biri «kod yoxdur» görüb iki kod yaradırdı. Advisory xact-kilid PgBouncer-in
    tranzaksiya rejimində də təhlükəsizdir.
    """
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            [f"accounts.email_otp:{purpose}:{email}"],
        )


def _resend_wait_seconds(otp: EmailOTP | None, *, now=None) -> int:
    """Bu koddan sonra yeni kod nə vaxt istənə bilər (saniyə, 0 = indi)."""
    if otp is None:
        return 0
    elapsed = ((now or timezone.now()) - otp.created_at).total_seconds()
    return max(0, math.ceil(get_auth_otp_resend_cooldown_seconds() - elapsed))


def issue_email_otp(
    user=None,
    *,
    email: str | None = None,
    purpose: str = EmailOTP.Purpose.SIGNUP,
    enforce_cooldown: bool = False,
    reuse_recent: bool = False,
):
    """Create a fresh OTP; keep the last ``OTP_ACCEPTED_RECENT_CODES`` live codes, retire older ones.

    ``reuse_recent=True`` (sahib 2026-10-21): resend cooldown daxilində eyni istifadəçi + məqsəd +
    e-poçt üçün qüvvədə kod varsa YENİ KOD YARADILMIR — ``(None, expires_at, mövcud_kod)`` qaytarılır
    (çağıran məktub göndərmir). İkiqat klik / səhifə keçidində təkrar göndəriş beləcə bir kod verir.
    """

    if user is not None:
        assert_account_access_allowed(user)
    elif staged_user_for_email(email) is not None:
        raise StagedAccountAccessError()

    normalized_email = _normalize_email(email or getattr(user, "email", ""))
    if not normalized_email:
        raise ValueError("A valid email address is required to issue an OTP.")

    with transaction.atomic():
        _lock_otp_scope(email=normalized_email, purpose=purpose)
        pending_qs = EmailOTP.pending_queryset(user=user, email=normalized_email, purpose=purpose)
        now = timezone.now()
        live = [otp for otp in pending_qs.select_for_update() if otp.expires_at > now]
        latest_live = live[0] if live else None

        retry_after = _resend_wait_seconds(latest_live, now=now)
        if retry_after > 0:
            if reuse_recent:
                return None, latest_live.expires_at, latest_live
            if enforce_cooldown:
                raise OTPResendCooldownError(retry_after=retry_after)

        recent_count, oldest_recent = _count_recent_sends(email=normalized_email)
        if recent_count >= get_auth_otp_max_sends_per_hour():
            retry_after = 3600
            if oldest_recent is not None:
                retry_after = max(1, int((oldest_recent.created_at + timedelta(hours=1) - now).total_seconds()))
            raise OTPRateLimitError(retry_after=retry_after)

        keep = [otp.pk for otp in live[: OTP_ACCEPTED_RECENT_CODES - 1]]
        pending_qs.exclude(pk__in=keep).update(is_used=True)

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


def _deliver_otp(*, code, expires_at, otp_record, email, user, purpose, request=None) -> None:
    """Kodu SİNXRON göndər; uğursuz olsa yaradılmış qeyd silinir (istifadəçi «göndərildi» görməsin)."""
    context = _build_email_context(
        user=user,
        email=email,
        purpose=purpose,
        code=code,
        request=request,
        expires_at=expires_at,
    )
    context["from_email"] = sender_for(purpose)
    try:
        _send_otp_message(email=email, purpose=purpose, context=context)
        logger.info("OTP email sent synchronously to %s for purpose %s", email, purpose)
    except Exception:
        otp_record.delete()
        logger.exception("OTP email delivery failed for %s", email)
        raise


def send_otp_email(
    email: str,
    *,
    user=None,
    purpose: str = EmailOTP.Purpose.LOGIN,
    request=None,
    enforce_cooldown: bool = False,
):
    """Generate, persist, and send an OTP email."""

    code, expires_at, otp_record = issue_email_otp(
        user,
        email=email,
        purpose=purpose,
        enforce_cooldown=enforce_cooldown,
    )
    normalized_email = _normalize_email(email or getattr(user, "email", ""))
    _deliver_otp(
        code=code,
        expires_at=expires_at,
        otp_record=otp_record,
        email=normalized_email,
        user=user,
        purpose=purpose,
        request=request,
    )
    return code


def request_email_otp(email: str, *, user=None, purpose: str, request=None) -> OTPSendResult:
    """İdempotent göndəriş (sahib 2026-10-21): cooldown daxilində təkrar sorğu YENİ KOD/MƏKTUB vermir.

    Cooldown keçəndən sonra yeni kod göndərilir, əvvəlki kod(lar) isə öz müddətinə qədər qəbul olunur
    (``OTP_ACCEPTED_RECENT_CODES``). Saatlıq limit ``OTPRateLimitError`` ilə qalır.
    """
    code, expires_at, otp_record = issue_email_otp(user, email=email, purpose=purpose, reuse_recent=True)
    if code is None:
        return OTPSendResult(reused=True, expires_at=expires_at, resend_available_in=_resend_wait_seconds(otp_record))
    _deliver_otp(
        code=code,
        expires_at=expires_at,
        otp_record=otp_record,
        email=_normalize_email(email or getattr(user, "email", "")),
        user=user,
        purpose=purpose,
        request=request,
    )
    return OTPSendResult(
        reused=False, expires_at=expires_at, resend_available_in=get_auth_otp_resend_cooldown_seconds()
    )


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
    expires_at = getattr(otp, "expires_at", None)
    now = timezone.now()
    return {
        "otp_expires_at": expires_at,
        # Sahib 2026-10-21: geri sayım SERVER saniyəsi ilə (istifadəçinin saatı səhvdirsə «vaxtı keçib» erkən görünmürdü).
        "otp_remaining_seconds": max(0, math.ceil((expires_at - now).total_seconds())) if expires_at else 0,
        "otp_resend_available_in": _resend_wait_seconds(otp, now=now) if expires_at and expires_at > now else 0,
        "otp_expiry_minutes": get_auth_otp_expiry_minutes(),
        "otp_expiry_seconds": get_auth_otp_expiry_seconds(),
    }


def _stale_code_reason(*, user, email: str, purpose: str, candidate: str, now) -> tuple[str, bool]:
    """Qüvvədə olmayan, amma ƏSL göndərilmiş kod daxil edilibsə səbəbi; ikinci dəyər — ən son kod
    çox səhv cəhdlə bağlanıbmı.

    Sahib 2026-10-21: əvəzlənmiş/istifadə olunmuş kod «vaxtı keçib» kimi göstərilirdi. Səbəb dəqiq
    deyilir; əsl kod olduğu üçün bu, səhv cəhd sayılmır (təxmin deyil).
    """
    recent = EmailOTP.objects.filter(email=email, purpose=purpose, created_at__gte=now - _STALE_LOOKBACK)
    if user is not None:
        recent = recent.filter(user=user)
    rows = list(recent.order_by("-created_at")[:10])
    max_attempts = get_auth_otp_max_attempts()
    newest = rows[0] if rows else None
    locked = bool(
        newest is not None
        and not newest.is_verified
        and newest.expires_at > now
        and int(newest.attempts_count or 0) >= max_attempts
    )
    for otp in rows:
        if not otp.matches_code(candidate):
            continue
        if otp.is_verified:
            return "already_used", locked
        if otp.expires_at <= now:
            return "expired", locked
        if locked or int(otp.attempts_count or 0) >= max_attempts:
            return "max_attempts", locked
        return "superseded", locked
    return "", locked


def _retire(otps) -> None:
    pks = [otp.pk for otp in otps if not otp.is_used]
    if pks:
        EmailOTP.objects.filter(pk__in=pks).update(is_used=True)


def consume_email_otp(otp: EmailOTP) -> None:
    """Uğurlu yoxlamadan sonra kodu işlət və eyni ünvan/məqsədin qalan kodlarını bağla."""
    EmailOTP.pending_queryset(user=otp.user, email=otp.email, purpose=otp.purpose).exclude(pk=otp.pk).update(
        is_used=True
    )
    otp.mark_verified()


def verify_email_otp(
    *,
    email: str,
    code: str,
    user=None,
    purpose: str = EmailOTP.Purpose.SIGNUP,
    consume: bool = True,
) -> OTPVerificationResult:
    """Kodu ünvan/məqsəd üçün qüvvədə olan son ``OTP_ACCEPTED_RECENT_CODES`` koddan biri ilə yoxla.

    ``consume=False`` — yalnız yoxla (parol validasiyası sonra gedən formalar ``consume_email_otp`` çağırır).
    """

    if user is not None:
        try:
            assert_account_access_allowed(user)
        except StagedAccountAccessError:
            return OTPVerificationResult(success=False, reason="access_denied")
    elif staged_user_for_email(email) is not None:
        return OTPVerificationResult(success=False, reason="access_denied")

    normalized_email = _normalize_email(email or getattr(user, "email", ""))
    candidate = "".join(character for character in str(code or "").strip() if character.isdigit())
    if not normalized_email or len(candidate) != 6:
        return OTPVerificationResult(success=False, reason="invalid_format")

    with transaction.atomic():
        pending_qs = EmailOTP.pending_queryset(user=user, email=normalized_email, purpose=purpose).select_for_update()
        pending = list(pending_qs[:10])
        now = timezone.now()
        live = [otp for otp in pending if otp.expires_at > now][:OTP_ACCEPTED_RECENT_CODES]
        expired = [otp for otp in pending if otp.expires_at <= now]
        _retire(expired)

        if not live:
            reason, locked = _stale_code_reason(
                user=user, email=normalized_email, purpose=purpose, candidate=candidate, now=now
            )
            if not reason:
                reason = "expired" if expired else ("max_attempts" if locked else "missing")
            return OTPVerificationResult(success=False, reason=reason)

        latest = live[0]
        if int(latest.attempts_count or 0) >= get_auth_otp_max_attempts():
            _retire(live)
            return OTPVerificationResult(success=False, reason="max_attempts", remaining_attempts=0)

        matched = next((otp for otp in live if otp.matches_code(candidate)), None)
        if matched is None:
            stale, _locked = _stale_code_reason(
                user=user, email=normalized_email, purpose=purpose, candidate=candidate, now=now
            )
            if stale:
                return OTPVerificationResult(success=False, reason=stale, expires_at=latest.expires_at)
            latest.register_failed_attempt()
            if latest.remaining_attempts <= 0:
                _retire(live)
                return OTPVerificationResult(success=False, reason="max_attempts", remaining_attempts=0)
            return OTPVerificationResult(
                success=False,
                reason="invalid",
                remaining_attempts=latest.remaining_attempts,
                expires_at=latest.expires_at,
            )

        if consume:
            consume_email_otp(matched)
        return OTPVerificationResult(
            success=True, otp=matched, remaining_attempts=matched.remaining_attempts, expires_at=matched.expires_at
        )


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

    assert_account_access_allowed(user)
    user.is_active = True
    user.save(update_fields=["is_active"])
    return activate_verified_membership(user)


__all__ = [
    "OTP_ACCEPTED_RECENT_CODES",
    "OTPRateLimitError",
    "OTPResendCooldownError",
    "OTPSendResult",
    "OTPVerificationResult",
    "activate_user_account",
    "consume_email_otp",
    "get_otp_timer_context",
    "issue_email_otp",
    "request_email_otp",
    "send_login_otp",
    "send_otp_email",
    "send_verification_otp",
    "verify_email_otp",
    "verify_otp_code",
]
