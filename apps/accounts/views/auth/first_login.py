"""First-login flow for administration-provisioned accounts.

E-university accounts are created by the administration (no public self-signup).
On the very first login the user signs in with a temporary password and is then
forced — by ``FirstLoginPasswordMiddleware`` — to:

  1. confirm/enter their email and receive a one-time code (OTP),
  2. enter the code and set their own password.

After that the email is marked verified (usable for password recovery) and the
``password_change_required`` flag is cleared, unlocking the rest of the system.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.utils.translation import pgettext

from apps.accounts.identity import canonical_identity_queryset
from apps.accounts.models import EmailOTP
from core.rate_limit import is_rate_limited, record_rate_limit_hit

from ...services import send_otp_email, verify_email_otp
from ._shared import _otp_limit_key, _validate_otp_email
from .constants import User

_CTX = "accounts.first_login"
_OTP_SENT_SESSION_KEY = "first_login_otp_sent_email"


def _email_taken_by_another_account(email, user) -> bool:
    """E-poçt BAŞQA hesaba məxsusdursa ``True`` (kanonik unikal indekslə eyni forma).

    2026-09-13 access auditi, F-08: ilk-giriş axını istənilən e-poçta OTP
    göndərirdi — o cümlədən başqa istifadəçinin qeydiyyatlı ünvanına (spam +
    kod ələ keçirilsə e-poçt kimliyinin «oğurlanması» cəhdi) — və OTP təsdiqi
    ilə ``user.email`` yazılanda ``accounts_auth_email_canon_uniq`` indeksi
    ``IntegrityError`` → 500 verirdi. Yoxlama göndərişdən ƏVVƏL edilir.
    """
    return canonical_identity_queryset(User.objects.all(), "email", email).exclude(pk=user.pk).exists()


def _email_unavailable_message():
    return pgettext(_CTX, "Bu email ünvanı istifadə oluna bilməz. Başqa ünvan daxil edin.")


def _profile_requires_first_login(user) -> bool:
    profile = getattr(user, "profile", None)
    return bool(profile is not None and getattr(profile, "password_change_required", False))


@login_required
def set_initial_password_view(request):
    """Two-step first-login: verify email via OTP, then set a new password."""
    user = request.user
    if not _profile_requires_first_login(user):
        # Nothing to do — the account is already set up.
        return redirect("accounts:profile")

    prefilled_email = (request.session.get(_OTP_SENT_SESSION_KEY) or user.email or "").strip()
    otp_sent = bool(request.session.get(_OTP_SENT_SESSION_KEY))

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "send_otp":
            return _handle_send_otp(request, user)
        if action == "set_password":
            return _handle_set_password(request, user)

    return render(
        request,
        "accounts/first_login_set_password.html",
        {
            "email": prefilled_email,
            "otp_sent": otp_sent,
            "user_display": user.get_full_name() or user.username,
        },
    )


def _handle_send_otp(request, user):
    raw_email = request.POST.get("email", "").strip()
    try:
        email = _validate_otp_email(raw_email)
    except ValidationError:
        messages.error(request, pgettext(_CTX, "Etibarlı email ünvanı daxil edin."))
        return redirect("accounts:set_initial_password")

    # Throttle OTP sends per (user, email) to prevent email-bombing.
    rate = getattr(settings, "OTP_RESEND_RATE_LIMIT", "5/10m")
    limit_key = _otp_limit_key(request, email)
    is_limited, _retry_after = is_rate_limited("first_login_otp", rate, *limit_key)
    if is_limited:
        messages.error(request, pgettext(_CTX, "Çox sayda cəhd. Bir az sonra yenidən yoxlayın."))
        return redirect("accounts:set_initial_password")

    # F-08 (2026-09-13): başqa hesabın e-poçtuna kod göndərilmir (spam +
    # sonrakı unikal-indeks 500-ünün qarşısı). Cəhd rate-limitdə sayılır.
    if _email_taken_by_another_account(email, user):
        record_rate_limit_hit("first_login_otp", rate, *limit_key)
        messages.error(request, _email_unavailable_message())
        return redirect("accounts:set_initial_password")

    try:
        send_otp_email(email, user=user, purpose=EmailOTP.Purpose.PASSWORD_RESET, request=request)
    except Exception:
        messages.error(request, pgettext(_CTX, "Kod göndərilə bilmədi. Zəhmət olmasa yenidən cəhd edin."))
        return redirect("accounts:set_initial_password")

    record_rate_limit_hit("first_login_otp", rate, *limit_key)
    request.session[_OTP_SENT_SESSION_KEY] = email
    messages.success(request, pgettext(_CTX, "Təsdiq kodu email ünvanınıza göndərildi."))
    return redirect("accounts:set_initial_password")


def _handle_set_password(request, user):
    email = (request.session.get(_OTP_SENT_SESSION_KEY) or "").strip()
    if not email:
        messages.error(request, pgettext(_CTX, "Əvvəlcə email ünvanınızı təsdiqləyin."))
        return redirect("accounts:set_initial_password")

    code = request.POST.get("code", "").strip()
    password1 = request.POST.get("password1", "")
    password2 = request.POST.get("password2", "")

    if password1 != password2:
        messages.error(request, pgettext(_CTX, "Parollar uyğun gəlmir."))
        return redirect("accounts:set_initial_password")

    try:
        validate_password(password1, user=user)
    except ValidationError as exc:
        for message in exc.messages:
            messages.error(request, message)
        return redirect("accounts:set_initial_password")

    verification = verify_email_otp(email=email, code=code, user=user, purpose=EmailOTP.Purpose.PASSWORD_RESET)
    if not verification.success:
        messages.error(request, pgettext(_CTX, "Kod yanlış və ya vaxtı keçib. Yenidən cəhd edin."))
        return redirect("accounts:set_initial_password")

    # Persist the new credential + verified email, then clear the flag.
    # F-08 (2026-09-13): göndəriş ilə təsdiq arasında e-poçt başqa hesaba
    # verilibsə (yarış) unikal indeks ``IntegrityError`` atır — 500 əvəzinə
    # mesajla geri qaytarılır; parol da dəyişmir (atomik blok).
    user.email = email
    user.set_password(password1)
    try:
        with transaction.atomic():
            user.save(update_fields=["email", "password"])
    except IntegrityError:
        user.refresh_from_db(fields=["email", "password"])
        request.session.pop(_OTP_SENT_SESSION_KEY, None)
        messages.error(request, _email_unavailable_message())
        return redirect("accounts:set_initial_password")
    update_session_auth_hash(request, user)  # keep the user logged in after set_password

    profile = user.profile
    profile.email_verified = True
    profile.password_change_required = False
    profile.save(update_fields=["email_verified", "password_change_required", "updated_at"])

    request.session.pop(_OTP_SENT_SESSION_KEY, None)
    messages.success(request, pgettext(_CTX, "Parolunuz təyin olundu. Sistemə xoş gəlmisiniz!"))
    return redirect("accounts:profile")
