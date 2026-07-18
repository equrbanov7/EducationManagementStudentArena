"""
Helpers for the hardened Django admin authentication flow.
"""

from __future__ import annotations

import logging

from django import forms
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from core.rate_limit import clear_rate_limit, is_rate_limited, normalize_rate_identity, record_rate_limit_hit
from core.utils import get_auth_otp_expiry_minutes, get_client_ip

logger = logging.getLogger(__name__)

ADMIN_2FA_PENDING_USER_SESSION_KEY = "admin_2fa_pending_user_id"
ADMIN_2FA_VERIFIED_USER_SESSION_KEY = "admin_2fa_verified_user_id"
ADMIN_2FA_NEXT_URL_SESSION_KEY = "admin_2fa_next_url"
ADMIN_OTP_VERIFY_SCOPE = "admin.otp.verify"
ADMIN_OTP_RESEND_SCOPE = "admin.otp.resend"
DEFAULT_ADMIN_OTP_VERIFY_RATE_LIMIT = "5/10m"
DEFAULT_ADMIN_OTP_RESEND_RATE_LIMIT = "3/10m"


class AdminOTPForm(forms.Form):
    code = forms.CharField(
        label="OTP kodu",
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "placeholder": "000000",
            }
        ),
    )

    def clean_code(self):
        code = "".join(character for character in str(self.cleaned_data.get("code", "")).strip() if character.isdigit())
        if len(code) != 6:
            raise forms.ValidationError("6 rəqəmli OTP kodu daxil edin.")
        return code


def admin_2fa_required_for_user(user) -> bool:
    return bool(
        getattr(settings, "ADMIN_2FA_REQUIRED", False)
        and user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and getattr(user, "is_staff", False)
    )


def admin_2fa_verified(request) -> bool:
    user = getattr(request, "user", None)
    if not admin_2fa_required_for_user(user):
        return True
    expected_user_id = str(getattr(user, "pk", ""))
    verified_user_id = str(request.session.get(ADMIN_2FA_VERIFIED_USER_SESSION_KEY, ""))
    return bool(expected_user_id and verified_user_id == expected_user_id)


def clear_admin_2fa_state(request) -> None:
    for key in (
        ADMIN_2FA_PENDING_USER_SESSION_KEY,
        ADMIN_2FA_VERIFIED_USER_SESSION_KEY,
        ADMIN_2FA_NEXT_URL_SESSION_KEY,
    ):
        request.session.pop(key, None)


def mark_admin_2fa_pending(request, *, next_url: str = "") -> None:
    user = getattr(request, "user", None)
    clear_admin_2fa_state(request)
    if user and getattr(user, "is_authenticated", False):
        request.session[ADMIN_2FA_PENDING_USER_SESSION_KEY] = str(user.pk)
    if next_url:
        request.session[ADMIN_2FA_NEXT_URL_SESSION_KEY] = next_url
    request.session.modified = True


def mark_admin_2fa_verified(request) -> None:
    user = getattr(request, "user", None)
    if user and getattr(user, "is_authenticated", False):
        request.session[ADMIN_2FA_VERIFIED_USER_SESSION_KEY] = str(user.pk)
    request.session.pop(ADMIN_2FA_PENDING_USER_SESSION_KEY, None)
    request.session.modified = True


def admin_2fa_pending_for_request(request) -> bool:
    user = getattr(request, "user", None)
    if not admin_2fa_required_for_user(user):
        return False
    return str(request.session.get(ADMIN_2FA_PENDING_USER_SESSION_KEY, "")) == str(getattr(user, "pk", ""))


def pop_admin_2fa_next_url(request, default_url: str) -> str:
    next_url = str(request.session.pop(ADMIN_2FA_NEXT_URL_SESSION_KEY, "") or "").strip()
    if not next_url.startswith("/"):
        return default_url
    return next_url


def admin_otp_limit_keys(request, *, user=None) -> tuple[str, str]:
    client_ip = get_client_ip(request) or "unknown"
    identity = normalize_rate_identity(
        getattr(user, "email", "") or getattr(user, "username", "") or getattr(user, "pk", "")
    )
    return client_ip, identity


def get_admin_otp_verify_rate_limit() -> str:
    return getattr(settings, "ADMIN_OTP_VERIFY_RATE_LIMIT", DEFAULT_ADMIN_OTP_VERIFY_RATE_LIMIT)


def get_admin_otp_resend_rate_limit() -> str:
    return getattr(settings, "ADMIN_OTP_RESEND_RATE_LIMIT", DEFAULT_ADMIN_OTP_RESEND_RATE_LIMIT)


def send_admin_otp_email(user, *, request=None) -> tuple[str, object]:
    # M3 (2026-07-02): accounts OTP servisi hook üzərindən (core.auth_otp) —
    # core→accounts import kənarını kəsir; model lazy get_model ilə.
    from django.apps import apps as django_apps

    from core.auth_otp import issue_email_otp

    EmailOTP = django_apps.get_model("accounts", "EmailOTP")
    code, expires_at, _otp = issue_email_otp(user, purpose=EmailOTP.Purpose.ADMIN_LOGIN)
    context = {
        "brand": getattr(settings, "SITE_BRAND_NAME", "") or "EMSArena",
        "user": user,
        "code": code,
        "otp_expiry_minutes": get_auth_otp_expiry_minutes(),
        "request": request,
    }
    text_body = render_to_string("admin/emails/admin_otp_email.txt", context)
    html_body = render_to_string("admin/emails/admin_otp_email.html", context)

    message = EmailMultiAlternatives(
        subject="Admin giriş təsdiqi",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(html_body, "text/html")
    message.send()
    return code, expires_at


def log_admin_security_event(
    *, action: str, request, user=None, reason: str, resource_type: str, resource_id: str = ""
):
    from core.audit import log_action

    try:
        log_action(
            action=action,
            user=user,
            reason=reason,
            request=request,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_repr=resource_type.replace("_", " ").title(),
        )
    except Exception:
        logger.exception("Failed to write admin security audit log for action %s", action)


class AdminOTPGateMiddleware:
    """Admin 2FA gate — parol keçmiş, OTP hələ təsdiqlənməmiş admin istifadəçini
    OTP təsdiq səhifəsindən BAŞQA HƏR YERDƏN saxlayır.

    Kök problem: Django admin login parol doğrulandıqda dərhal
    ``django.contrib.auth.login()`` çağırır — yəni session TAM authenticated
    olur, SONRA OTP challenge qoyulur (``mark_admin_2fa_pending``). OTP gate isə
    yalnız admin site-ın ``has_permission``-ında yoxlanır, ona görə istifadəçi
    OTP-ni keçmədən başqa tab-da ``/accounts/profile/`` (və ya istənilən
    ``@login_required`` səhifə) yaza bilir və girirdi — 2FA bypass.

    Middleware OTP TƏSDİQLƏNMƏYƏN admin session-u (harada login olursa olsun —
    admin login, ƏSAS sayt login-i ``/accounts/login/``, force_login, session
    bərpası) ``admin:verify-otp``-dan başqa hər yerdən saxlayır. Yalnız staff +
    ``ADMIN_2FA_REQUIRED`` + təsdiqlənməmiş halda işə düşür — adi istifadəçilərə
    və OTP-si təsdiqlənmiş adminlərə heç bir təsir yoxdur. İstisna: verify-otp/
    resend-otp, logout (imtina), statik/media. Challenge (OTP email) verify-otp
    görünüşündə bootstrap olunur — email göndərmə məntiqi bir yerdə qalır.

    QEYD: yalnız ``admin login``-i qorumaq kifayət deyildi — is_staff superadmin
    ƏSAS sayt login-i ilə OTP-siz girə bilirdi (challenge heç başlamırdı). Ona
    görə şərt ``pending`` yox, ``not verified``-dır.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self._exempt_cache = None

    def _exempt_prefixes(self):
        # reverse() lazy: URLConf hazır olandan sonra bir dəfə hesablanır.
        if self._exempt_cache is None:
            from django.conf import settings
            from django.urls import NoReverseMatch, reverse

            prefixes = []
            for name in ("admin:verify-otp", "admin:resend-otp", "admin:logout"):
                try:
                    prefixes.append(reverse(name))
                except NoReverseMatch:
                    continue
            for attr in ("STATIC_URL", "MEDIA_URL"):
                value = getattr(settings, attr, "") or ""
                if value.startswith("/"):
                    prefixes.append(value)
            self._exempt_cache = tuple(p for p in prefixes if p)
        return self._exempt_cache

    def __call__(self, request):
        user = getattr(request, "user", None)
        if admin_2fa_required_for_user(user) and not admin_2fa_verified(request):
            path = request.path_info
            if not any(path.startswith(prefix) for prefix in self._exempt_prefixes()):
                from django.shortcuts import redirect
                from django.urls import reverse

                return redirect(reverse("admin:verify-otp"))
        return self.get_response(request)


def admin_verify_rate_limited(request, *, user) -> tuple[bool, int | None]:
    key_parts = admin_otp_limit_keys(request, user=user)
    return is_rate_limited(ADMIN_OTP_VERIFY_SCOPE, get_admin_otp_verify_rate_limit(), *key_parts)


def record_admin_verify_failure(request, *, user) -> tuple[bool, int | None]:
    key_parts = admin_otp_limit_keys(request, user=user)
    return record_rate_limit_hit(ADMIN_OTP_VERIFY_SCOPE, get_admin_otp_verify_rate_limit(), *key_parts)


def clear_admin_verify_rate_limit(request, *, user) -> None:
    clear_rate_limit(ADMIN_OTP_VERIFY_SCOPE, *admin_otp_limit_keys(request, user=user))


def admin_resend_rate_limited(request, *, user) -> tuple[bool, int | None]:
    key_parts = admin_otp_limit_keys(request, user=user)
    return is_rate_limited(ADMIN_OTP_RESEND_SCOPE, get_admin_otp_resend_rate_limit(), *key_parts)


def record_admin_resend_hit(request, *, user) -> tuple[bool, int | None]:
    key_parts = admin_otp_limit_keys(request, user=user)
    return record_rate_limit_hit(ADMIN_OTP_RESEND_SCOPE, get_admin_otp_resend_rate_limit(), *key_parts)
