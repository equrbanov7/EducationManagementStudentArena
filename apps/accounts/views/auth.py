"""
Authentication views: registration, verification, login, logout.
"""

import json
import logging
import re
import secrets
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.views import LoginView, PasswordResetConfirmView, PasswordResetView
from django.core.exceptions import ValidationError
from django.core.signing import BadSignature, SignatureExpired
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.translation import pgettext_lazy
from django.views.decorators.http import require_POST
from django.views.generic.edit import FormView

from apps.accounts.models import EmailOTP
from apps.organizations.services import is_tenant_accessible_organization
from core.helpers import _safe_same_origin_redirect_path
from core.rate_limit import clear_rate_limit, is_rate_limited, normalize_rate_identity, record_rate_limit_hit
from core.tenancy import restore_request_organization_from_profile
from core.utils import get_auth_otp_expiry_minutes, get_client_ip

from ..forms import (
    CustomLoginForm,
    CustomPasswordResetForm,
    OTPPasswordResetCodeForm,
    OTPPasswordResetConfirmForm,
    RegisterForm,
)
from ..middleware import POST_LOGIN_REDIRECT_GUARD_SESSION_KEY
from ..queries import get_signup_lookup_payload
from ..services import (
    OTPRateLimitError,
    OTPResendCooldownError,
    activate_user_account,
    clear_pending_registration,
    finalize_pending_registration,
    get_otp_timer_context,
    get_pending_registration,
    send_login_otp,
    send_otp_email,
    send_verification_otp,
    store_pending_registration,
    verify_email_otp,
)
from ._helpers import signer

logger = logging.getLogger(__name__)
User = get_user_model()

AUTH_RATE_LIMIT_MESSAGE = "Çox sayda cəhd edildi. Zəhmət olmasa bir az sonra yenidən cəhd edin."
AUTH_DEVICE_COOKIE_NAME = "ems_auth_device"
AUTH_DEVICE_COOKIE_SALT = "accounts.auth_device"  # nosec B105 - signing salt, not a secret.
AUTH_DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365
AUTH_DEVICE_ID_RE = re.compile(r"^[a-f0-9]{32,64}$")
LOGIN_LIMIT_SCOPE_DEVICE = "accounts.login.device"
LOGIN_LIMIT_SCOPE_IDENTITY = "accounts.login.identity"
OTP_VERIFY_LIMIT_SCOPE = "accounts.otp.verify"
OTP_RESEND_LIMIT_SCOPE = "accounts.otp.resend"
AUTH_REDIRECT_MAX_LENGTH = 2048
AUTH_REDIRECT_DISALLOWED_CHARS = frozenset({"'", '"', "\\", "\r", "\n", "\t"})
PASSWORD_RESET_EMAIL_SESSION_KEY = "accounts_password_reset_email"


def _new_auth_device_id():
    return secrets.token_hex(24)


def _get_auth_device_id(request):
    cached_device_id = getattr(request, "_accounts_auth_device_id", "")
    if cached_device_id:
        return cached_device_id

    try:
        signed_device_id = request.get_signed_cookie(
            AUTH_DEVICE_COOKIE_NAME,
            default="",
            salt=AUTH_DEVICE_COOKIE_SALT,
            max_age=AUTH_DEVICE_COOKIE_MAX_AGE,
        )
    except BadSignature:
        signed_device_id = ""

    candidate = str(signed_device_id or "").strip().lower()
    if AUTH_DEVICE_ID_RE.fullmatch(candidate):
        device_id = candidate
        needs_cookie = False
    else:
        device_id = _new_auth_device_id()
        needs_cookie = True

    request._accounts_auth_device_id = device_id
    request._accounts_auth_device_cookie_needs_refresh = needs_cookie
    return device_id


def _ensure_auth_device_cookie(request, response):
    device_id = getattr(request, "_accounts_auth_device_id", "") or _get_auth_device_id(request)
    if not getattr(request, "_accounts_auth_device_cookie_needs_refresh", False):
        return response

    response.set_signed_cookie(
        AUTH_DEVICE_COOKIE_NAME,
        device_id,
        salt=AUTH_DEVICE_COOKIE_SALT,
        max_age=AUTH_DEVICE_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure(),
    )
    return response


def _login_limit_keys(request, username):
    device_id = _get_auth_device_id(request)
    normalized_username = normalize_rate_identity(username)
    return [
        (LOGIN_LIMIT_SCOPE_DEVICE, device_id),
        (LOGIN_LIMIT_SCOPE_IDENTITY, device_id, normalized_username),
    ]


def _clear_login_rate_limits_after_password_reset(request, user):
    device_id = _get_auth_device_id(request)
    clear_rate_limit(LOGIN_LIMIT_SCOPE_DEVICE, device_id)

    identities = {
        getattr(user, "username", ""),
        getattr(user, "email", ""),
    }
    for identity in identities:
        if identity:
            clear_rate_limit(LOGIN_LIMIT_SCOPE_IDENTITY, device_id, normalize_rate_identity(identity))


def _authenticate_superadmin_for_rate_limit_reset(request, username, password):
    if not username or not password:
        return None

    user = authenticate(request=request, username=username, password=password)
    if user is None:
        return None

    if user.is_superuser or getattr(user, "is_superadmin", False):
        return user
    return None


def _otp_limit_key(request, email):
    return (
        get_client_ip(request) or "unknown",
        normalize_rate_identity(email),
    )


def _sanitize_auth_redirect_target(request, candidate_url):
    safe_path = _safe_same_origin_redirect_path(request, candidate_url)
    if not safe_path:
        return ""

    if len(safe_path) > AUTH_REDIRECT_MAX_LENGTH:
        return ""

    if not safe_path.startswith("/"):
        return ""

    if any(character in AUTH_REDIRECT_DISALLOWED_CHARS for character in safe_path):
        return ""

    return safe_path


def _load_request_payload(request):
    if request.content_type == "application/json":
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except (TypeError, ValueError):
            return {}
    return request.POST


def _validate_otp_email(value):
    email = EmailOTP.normalize_email(value)
    if not email or "@" not in email:
        raise ValidationError("Etibarlı email ünvanı daxil edin.")
    return email


def _resolve_otp_purpose(value, *, default=EmailOTP.Purpose.LOGIN):
    candidate = str(value or "").strip().lower()
    allowed = {
        EmailOTP.Purpose.SIGNUP,
        EmailOTP.Purpose.LOGIN,
        EmailOTP.Purpose.PASSWORD_RESET,
    }
    if candidate in allowed:
        return candidate
    return default


def _json_error(message, *, status=400, retry_after=None, **extra):
    payload = {"success": False, "detail": message}
    payload.update(extra)
    response = JsonResponse(payload, status=status)
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
    return response


class CustomLoginView(LoginView):
    """Login view with custom form and suspended-organization checks."""

    template_name = "accounts/login.html"
    authentication_form = CustomLoginForm
    redirect_authenticated_user = True
    # SEO: the login page is indexable (it carries brand keywords) but
    # ranks low. These values flow into the shared head partial.
    extra_context = {
        "seo_title": "Daxil ol | EMSArena",
        "seo_description": (
            "EMSArena hesabınıza daxil olun və təhsil, imtahan, kurs və " "idarəetmə panelindən istifadə edin."
        ),
    }

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        return _ensure_auth_device_cookie(request, response)

    def get_redirect_url(self):
        redirect_to = self.request.POST.get(
            self.redirect_field_name,
            self.request.GET.get(self.redirect_field_name),
        )
        return _sanitize_auth_redirect_target(self.request, redirect_to)

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        limit_keys = _login_limit_keys(request, username)

        for scope, *key_parts in limit_keys:
            is_limited, retry_after = is_rate_limited(scope, settings.LOGIN_RATE_LIMIT, *key_parts)
            if is_limited:
                superadmin_user = _authenticate_superadmin_for_rate_limit_reset(request, username, password)
                if superadmin_user is not None:
                    for reset_scope, *reset_key_parts in limit_keys:
                        clear_rate_limit(reset_scope, *reset_key_parts)
                    form.user_cache = superadmin_user
                    logger.warning(
                        "Cleared login rate limit after successful superadmin authentication",
                        extra={
                            "username": normalize_rate_identity(username),
                            "auth_device": _get_auth_device_id(request),
                            "client_ip": get_client_ip(request) or "unknown",
                        },
                    )
                    return self.form_valid(form)

                form.add_error(None, AUTH_RATE_LIMIT_MESSAGE)
                response = self.render_to_response(self.get_context_data(form=form), status=429)
                if retry_after:
                    response.headers["Retry-After"] = str(retry_after)
                return response

        if form.is_valid():
            for scope, *key_parts in limit_keys:
                clear_rate_limit(scope, *key_parts)
            return self.form_valid(form)

        for scope, *key_parts in limit_keys:
            record_rate_limit_hit(scope, settings.LOGIN_RATE_LIMIT, *key_parts)
        return self.form_invalid(form)

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session[POST_LOGIN_REDIRECT_GUARD_SESSION_KEY] = True
        return response


class NamespacedPasswordResetView(PasswordResetView):
    """Password reset view that sends an OTP and keeps the reset on-site."""

    template_name = "accounts/password_reset.html"
    form_class = CustomPasswordResetForm
    subject_template_name = "accounts/password_reset_subject.txt"
    email_template_name = "accounts/password_reset_email.txt"
    html_email_template_name = "accounts/password_reset_email.html"
    success_url = reverse_lazy("accounts:password_reset_done")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["otp_expiry_minutes"] = get_auth_otp_expiry_minutes()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        reset_users = getattr(form, "password_reset_users", [])
        if reset_users:
            reset_email = EmailOTP.normalize_email(form.cleaned_data["email"])
            self.request.session[PASSWORD_RESET_EMAIL_SESSION_KEY] = reset_email
        else:
            self.request.session.pop(PASSWORD_RESET_EMAIL_SESSION_KEY, None)
        return response


class NamespacedPasswordResetDoneView(FormView):
    template_name = "accounts/password_reset_done.html"
    form_class = OTPPasswordResetCodeForm
    success_url = reverse_lazy("accounts:password_reset_complete")

    def get_reset_email(self):
        return EmailOTP.normalize_email(self.request.session.get(PASSWORD_RESET_EMAIL_SESSION_KEY, ""))

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["email"] = self.get_reset_email()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        reset_email = self.get_reset_email()
        if reset_email:
            context.update(get_otp_timer_context(email=reset_email, purpose=EmailOTP.Purpose.PASSWORD_RESET))
        else:
            context["otp_expires_at"] = None
            context["otp_expiry_seconds"] = settings.AUTH_OTP_EXPIRY_SECONDS
        context["otp_expiry_minutes"] = get_auth_otp_expiry_minutes()
        context["password_reset_email"] = reset_email
        return context

    def form_valid(self, form):
        user = form.save()
        _clear_login_rate_limits_after_password_reset(self.request, user)
        self.request.session.pop(PASSWORD_RESET_EMAIL_SESSION_KEY, None)
        return super().form_valid(form)


class NamespacedPasswordResetConfirmView(PasswordResetConfirmView):
    """Password reset confirm view with namespaced completion redirect."""

    template_name = "accounts/password_reset_confirm.html"
    form_class = OTPPasswordResetConfirmForm
    success_url = reverse_lazy("accounts:password_reset_complete")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if getattr(self, "user", None) is not None and getattr(self.user, "is_authenticated", False):
            context.update(get_otp_timer_context(self.user, purpose=EmailOTP.Purpose.PASSWORD_RESET))
        else:
            context["otp_expires_at"] = None
            context["otp_expiry_minutes"] = get_auth_otp_expiry_minutes()
            context["otp_expiry_seconds"] = settings.AUTH_OTP_EXPIRY_SECONDS
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        user = getattr(form, "user", None) or getattr(self, "user", None)
        if user is not None:
            _clear_login_rate_limits_after_password_reset(self.request, user)
        self.request.session.pop(PASSWORD_RESET_EMAIL_SESSION_KEY, None)
        return response


# SEO metadata for the public register page. Merged into the GET-render
# context so the shared head partial (templates/partials/_seo_head.html)
# renders a brand-appropriate title and description.
_REGISTER_SEO = {
    "seo_title": "Hesab yaradın | EMSArena",
    "seo_description": (
        "EMSArena-da təşkilat, müəllim və ya tələbə hesabı yaradın və " "rəqəmsal təhsil platformasına qoşulun."
    ),
}


def register_view(request):
    """Start registration by caching the payload and sending a signup OTP."""
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            try:
                pending_registration = store_pending_registration(form.cleaned_data)
                send_otp_email(
                    pending_registration["email"],
                    purpose=EmailOTP.Purpose.SIGNUP,
                    request=request,
                )
            except OTPRateLimitError as exc:
                logger.warning(
                    "Signup OTP throttled for %s with retry_after=%s",
                    form.cleaned_data.get("email"),
                    exc.retry_after,
                )
                messages.error(request, "Bu email üçün saatlıq OTP limiti dolub. Bir az sonra yenidən cəhd edin.")
                response = render(
                    request,
                    "accounts/register.html",
                    {
                        "form": form,
                        "lookup_payload": get_signup_lookup_payload(),
                    },
                    status=429,
                )
                response.headers["Retry-After"] = str(exc.retry_after)
                return response
            except Exception:
                logger.exception("Registration failed during pending signup OTP delivery")
                messages.error(
                    request,
                    pgettext_lazy("accounts.auth.message", "registration_email_send_failed"),
                )
                return render(
                    request,
                    "accounts/register.html",
                    {
                        "form": form,
                        "lookup_payload": get_signup_lookup_payload(),
                    },
                )
            request.session["pending_verify_email"] = pending_registration["email"]

            # Preserve any ?next= parameter so it can be forwarded to the
            # login redirect after OTP verification completes (BUG-04 fix).
            next_url = _sanitize_auth_redirect_target(request, request.POST.get("next", request.GET.get("next", "")))
            if next_url:
                request.session["pending_next_url"] = next_url

            messages.success(
                request,
                pgettext_lazy("accounts.auth.message", "registration_completed_you_can_login_now"),
            )
            messages.success(request, pgettext_lazy("accounts.auth.message", "new_code_sent"))
            return redirect("accounts:verify_code")
    else:
        form = RegisterForm()

    return render(
        request,
        "accounts/register.html",
        {
            "form": form,
            "lookup_payload": get_signup_lookup_payload(),
            **_REGISTER_SEO,
        },
    )


def verify_code_view(request):
    """Verify email using OTP code."""
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(request, pgettext_lazy("accounts.auth.message", "verification_email_not_found_register_again"))
        return redirect("accounts:register")

    if request.method == "POST":
        code = request.POST.get("code", "").strip()

        user = User.objects.filter(email=email).first()
        pending_registration = get_pending_registration(email)
        if not user:
            if not pending_registration:
                messages.error(request, pgettext_lazy("accounts.auth.message", "user_not_found"))
                return redirect("accounts:register")

        otp_limit_key = _otp_limit_key(request, email)
        is_limited, retry_after = is_rate_limited(
            OTP_VERIFY_LIMIT_SCOPE,
            settings.OTP_VERIFY_RATE_LIMIT,
            *otp_limit_key,
        )
        context = {
            "email": email,
            **get_otp_timer_context(user, email=email, purpose=EmailOTP.Purpose.SIGNUP),
        }
        if is_limited:
            messages.error(request, AUTH_RATE_LIMIT_MESSAGE)
            response = render(request, "accounts/verify_code.html", context, status=429)
            if retry_after:
                response.headers["Retry-After"] = str(retry_after)
            return response

        verification = verify_email_otp(
            email=email,
            code=code,
            user=user,
            purpose=EmailOTP.Purpose.SIGNUP,
        )
        if not verification.success or verification.otp is None:
            record_rate_limit_hit(
                OTP_VERIFY_LIMIT_SCOPE,
                settings.OTP_VERIFY_RATE_LIMIT,
                *otp_limit_key,
            )
            messages.error(request, pgettext_lazy("accounts.auth.message", "code_invalid_or_expired"))
            return render(
                request,
                "accounts/verify_code.html",
                {
                    "email": email,
                    **get_otp_timer_context(user, email=email, purpose=EmailOTP.Purpose.SIGNUP),
                },
            )

        clear_rate_limit(OTP_VERIFY_LIMIT_SCOPE, *otp_limit_key)

        if user is None:
            try:
                user, organization, _requested_organization, _profile = finalize_pending_registration(email)
            except Exception:
                logger.exception("Failed to finalize pending registration for %s after OTP verification", email)
                messages.error(request, "OTP təsdiqləndi, amma hesab yaradılarkən xəta baş verdi. Yenidən cəhd edin.")
                return redirect("accounts:register")
            if is_tenant_accessible_organization(organization):
                request.session["active_organization"] = organization.slug
        else:
            joined_organization = activate_user_account(user)
            if is_tenant_accessible_organization(joined_organization):
                request.session["active_organization"] = joined_organization.slug
        request.session.pop("pending_verify_email", None)
        clear_pending_registration(email)

        messages.success(request, pgettext_lazy("accounts.auth.message", "email_verified_you_can_login_now"))

        # Restore the ?next= URL that was stored during registration so the
        # user lands on the originally requested page after logging in (BUG-04 fix).
        next_url = request.session.pop("pending_next_url", "")
        if next_url:
            login_url = reverse("accounts:login")
            return redirect(f"{login_url}?next={quote(next_url, safe='/:@')}")
        return redirect("accounts:login")

    user = User.objects.filter(email=email).first()
    return render(
        request,
        "accounts/verify_code.html",
        {
            "email": email,
            **get_otp_timer_context(user, email=email, purpose=EmailOTP.Purpose.SIGNUP),
        },
    )


def verify_email_link_view(request):
    """Verify email using signed token link."""
    token = request.GET.get("token", "")
    try:
        user_id = signer.unsign(token, max_age=settings.AUTH_OTP_EXPIRY_SECONDS)
        user = User.objects.get(pk=user_id)
        EmailOTP.objects.filter(
            user=user,
            purpose=EmailOTP.Purpose.SIGNUP,
            is_used=False,
        ).update(is_used=True, is_verified=True)
        joined_organization = activate_user_account(user)
        if is_tenant_accessible_organization(joined_organization):
            request.session["active_organization"] = joined_organization.slug
        request.session.pop("pending_verify_email", None)
        messages.success(request, pgettext_lazy("accounts.auth.message", "email_verified_you_can_login_now"))

        # Restore the ?next= URL that was stored during registration (BUG-04 fix).
        next_url = request.session.pop("pending_next_url", "")
        if next_url:
            login_url = reverse("accounts:login")
            return redirect(f"{login_url}?next={quote(next_url, safe='/:@')}")
        return redirect("accounts:login")
    except (BadSignature, SignatureExpired, User.DoesNotExist):
        messages.error(request, pgettext_lazy("accounts.auth.message", "link_invalid_or_expired"))
        return redirect("accounts:register")


@require_POST
def resend_code_view(request):
    """Resend email verification code."""
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(request, pgettext_lazy("accounts.auth.message", "email_not_found"))
        return redirect("accounts:register")

    user = User.objects.filter(email=email).first()
    pending_registration = get_pending_registration(email)
    if not user and not pending_registration:
        messages.error(request, pgettext_lazy("accounts.auth.message", "user_not_found"))
        return redirect("accounts:register")
    if user and user.is_active:
        messages.success(request, pgettext_lazy("accounts.auth.message", "email_verified_you_can_login_now"))
        return redirect("accounts:login")

    otp_limit_key = _otp_limit_key(request, email)
    is_limited, retry_after = record_rate_limit_hit(
        OTP_RESEND_LIMIT_SCOPE,
        settings.OTP_RESEND_RATE_LIMIT,
        *otp_limit_key,
    )
    if is_limited:
        messages.error(request, AUTH_RATE_LIMIT_MESSAGE)
        response = render(request, "accounts/verify_code.html", {"email": email}, status=429)
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response

    try:
        if user is not None:
            send_verification_otp(user, request=request, enforce_cooldown=True)
        else:
            send_otp_email(
                email,
                purpose=EmailOTP.Purpose.SIGNUP,
                request=request,
                enforce_cooldown=True,
            )
    except OTPResendCooldownError as exc:
        messages.error(request, f"Yeni OTP kodu üçün {exc.retry_after} saniyə gözləyin.")
        response = render(
            request,
            "accounts/verify_code.html",
            {
                "email": email,
                **get_otp_timer_context(user, email=email, purpose=EmailOTP.Purpose.SIGNUP),
            },
            status=429,
        )
        response.headers["Retry-After"] = str(exc.retry_after)
        return response
    except OTPRateLimitError as exc:
        messages.error(request, "Bu email üçün saatlıq OTP limiti dolub. Bir az sonra yenidən cəhd edin.")
        response = render(
            request,
            "accounts/verify_code.html",
            {
                "email": email,
                **get_otp_timer_context(user, email=email, purpose=EmailOTP.Purpose.SIGNUP),
            },
            status=429,
        )
        response.headers["Retry-After"] = str(exc.retry_after)
        return response

    messages.success(request, pgettext_lazy("accounts.auth.message", "new_code_sent"))
    return redirect("accounts:verify_code")


@require_POST
def send_otp_api_view(request):
    """JSON endpoint to issue login/signup OTP emails without exposing the OTP code."""

    payload = _load_request_payload(request)
    purpose = _resolve_otp_purpose(payload.get("purpose"), default=EmailOTP.Purpose.LOGIN)

    try:
        email = _validate_otp_email(payload.get("email", ""))
    except ValidationError as exc:
        return _json_error(str(exc.messages[0]))

    user = User.objects.filter(email__iexact=email).first()
    pending_registration = get_pending_registration(email)

    if purpose == EmailOTP.Purpose.LOGIN:
        if user is None or not user.is_active:
            return JsonResponse(
                {
                    "success": True,
                    "detail": "Əgər bu email qeydiyyatdan keçibsə, OTP göndərildi.",
                },
                status=202,
            )
        try:
            send_login_otp(email, request=request, user=user, enforce_cooldown=True)
        except OTPResendCooldownError as exc:
            return _json_error(
                "Yeni OTP kodu üçün bir az gözləyin.",
                status=429,
                retry_after=exc.retry_after,
                resend_available_in=exc.retry_after,
            )
        except OTPRateLimitError as exc:
            return _json_error(
                "Bu email üçün saatlıq OTP limiti dolub.",
                status=429,
                retry_after=exc.retry_after,
            )
        return JsonResponse(
            {
                "success": True,
                "detail": "OTP emailə göndərildi.",
                "expires_in": settings.AUTH_OTP_EXPIRY_SECONDS,
            },
            status=202,
        )

    if user is None and not pending_registration:
        return _json_error("Bu email üçün istifadəçi tapılmadı.", status=404)

    if purpose == EmailOTP.Purpose.SIGNUP and user is not None and user.is_active:
        return _json_error("Bu email artıq təsdiqlənib.", status=409)

    try:
        if user is not None:
            send_verification_otp(user, request=request, enforce_cooldown=True)
        else:
            send_otp_email(
                email,
                purpose=EmailOTP.Purpose.SIGNUP,
                request=request,
                enforce_cooldown=True,
            )
    except OTPResendCooldownError as exc:
        return _json_error(
            "Yeni OTP kodu üçün bir az gözləyin.",
            status=429,
            retry_after=exc.retry_after,
            resend_available_in=exc.retry_after,
        )
    except OTPRateLimitError as exc:
        return _json_error(
            "Bu email üçün saatlıq OTP limiti dolub.",
            status=429,
            retry_after=exc.retry_after,
        )

    return JsonResponse(
        {
            "success": True,
            "detail": "OTP emailə göndərildi.",
            "expires_in": settings.AUTH_OTP_EXPIRY_SECONDS,
        },
        status=202,
    )


@require_POST
def verify_otp_api_view(request):
    """JSON endpoint for verifying signup/login OTP codes."""

    payload = _load_request_payload(request)
    purpose = _resolve_otp_purpose(payload.get("purpose"), default=EmailOTP.Purpose.LOGIN)

    try:
        email = _validate_otp_email(payload.get("email", ""))
    except ValidationError as exc:
        return _json_error(str(exc.messages[0]))

    code = str(payload.get("otp", "")).strip()
    user = User.objects.filter(email__iexact=email).first()
    pending_registration = get_pending_registration(email)
    verification = verify_email_otp(
        email=email,
        code=code,
        user=user,
        purpose=purpose,
    )

    if not verification.success or verification.otp is None:
        return _json_error(
            "OTP yanlışdır, vaxtı bitib və ya maksimum cəhd limiti dolub.",
            status=400,
            remaining_attempts=verification.remaining_attempts,
            reason=verification.reason,
        )

    if purpose == EmailOTP.Purpose.SIGNUP:
        if user is None and pending_registration:
            user, organization, _requested_organization, _profile = finalize_pending_registration(email)
            if is_tenant_accessible_organization(organization):
                request.session["active_organization"] = organization.slug
        elif user is not None and not user.is_active:
            joined_organization = activate_user_account(user)
            if is_tenant_accessible_organization(joined_organization):
                request.session["active_organization"] = joined_organization.slug

    if purpose == EmailOTP.Purpose.LOGIN and user is not None and user.is_active:
        backend = settings.AUTHENTICATION_BACKENDS[0]
        login(request, user, backend=backend)
        restore_request_organization_from_profile(request, profile=getattr(user, "profile", None))
        request.session[POST_LOGIN_REDIRECT_GUARD_SESSION_KEY] = True

    request.session.pop("pending_verify_email", None)

    return JsonResponse(
        {
            "success": True,
            "detail": "OTP uğurla təsdiqləndi.",
            "verified": True,
            "authenticated": bool(purpose == EmailOTP.Purpose.LOGIN and user and user.is_active),
        }
    )


@require_POST
def resend_otp_api_view(request):
    """JSON endpoint to resend an OTP after the cooldown window."""

    payload = _load_request_payload(request)
    purpose = _resolve_otp_purpose(payload.get("purpose"), default=EmailOTP.Purpose.LOGIN)

    try:
        email = _validate_otp_email(payload.get("email", ""))
    except ValidationError as exc:
        return _json_error(str(exc.messages[0]))

    user = User.objects.filter(email__iexact=email).first()
    pending_registration = get_pending_registration(email)

    if purpose == EmailOTP.Purpose.LOGIN:
        if user is None or not user.is_active:
            return JsonResponse(
                {
                    "success": True,
                    "detail": "Əgər bu email qeydiyyatdan keçibsə, OTP göndərildi.",
                },
                status=202,
            )

        def send_callable():
            return send_login_otp(email, request=request, user=user, enforce_cooldown=True)

    else:
        if user is None and not pending_registration:
            return _json_error("Bu email üçün istifadəçi tapılmadı.", status=404)
        if user is not None:

            def send_callable():
                return send_verification_otp(user, request=request, enforce_cooldown=True)

        else:

            def send_callable():
                return send_otp_email(
                    email,
                    purpose=EmailOTP.Purpose.SIGNUP,
                    request=request,
                    enforce_cooldown=True,
                )

    try:
        send_callable()
    except OTPResendCooldownError as exc:
        return _json_error(
            "Resend üçün gözləmə vaxtı hələ bitməyib.",
            status=429,
            retry_after=exc.retry_after,
            resend_available_in=exc.retry_after,
        )
    except OTPRateLimitError as exc:
        return _json_error(
            "Bu email üçün saatlıq OTP limiti dolub.",
            status=429,
            retry_after=exc.retry_after,
        )

    return JsonResponse(
        {
            "success": True,
            "detail": "Yeni OTP göndərildi.",
            "expires_in": settings.AUTH_OTP_EXPIRY_SECONDS,
        },
        status=202,
    )


def logout_view(request):
    """Logout user and redirect to home.

    Only POST requests are accepted to prevent cross-site forced-logout attacks
    (e.g. an attacker embedding ``<img src="/accounts/logout/">`` on another page).
    GET requests receive HTTP 405 Method Not Allowed.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    logout(request)
    messages.success(request, pgettext_lazy("accounts.auth.message", "logout_success"))
    return redirect("home")
