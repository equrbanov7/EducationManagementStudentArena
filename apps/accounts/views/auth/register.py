"""accounts auth view paketi — register."""

from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.core.signing import BadSignature, SignatureExpired
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import pgettext, pgettext_lazy
from django.views.decorators.http import require_POST

from apps.accounts.models import EmailOTP
from apps.organizations.public import is_tenant_accessible_organization
from core.rate_limit import clear_rate_limit, is_rate_limited, record_rate_limit_hit

from ...forms import RegisterForm
from ...queries import get_signup_lookup_payload
from ...services import (
    OTPRateLimitError,
    OTPResendCooldownError,
    activate_user_account,
    clear_pending_registration,
    finalize_pending_registration,
    get_otp_timer_context,
    get_pending_registration,
    send_otp_email,
    send_verification_otp,
    store_pending_registration,
    verify_email_otp,
)
from .._helpers import signer
from ._shared import (
    _otp_limit_key,
    _sanitize_auth_redirect_target,
)
from .constants import (
    _REGISTER_SEO,
    AUTH_RATE_LIMIT_MESSAGE,
    OTP_RESEND_LIMIT_SCOPE,
    OTP_VERIFY_LIMIT_SCOPE,
    User,
    logger,
)


def _public_signup_enabled() -> bool:
    """Whether the public self-registration route is open.

    Default OFF (e-university provisioning model — accounts are created by the
    university administration; see docs/ACCOUNT_PROVISIONING.md). Controlled by
    ``settings.PUBLIC_SIGNUP_ENABLED`` (env: ``PUBLIC_SIGNUP_ENABLED``).
    """
    return bool(getattr(settings, "PUBLIC_SIGNUP_ENABLED", False))


def _signup_disabled_redirect(request):
    """Send the visitor to login with a clear "ask your administrator" notice."""
    messages.info(
        request,
        pgettext(
            "accounts.auth.message",
            "Hesablar universitet administrasiyası tərəfindən yaradılır. "
            "Giriş məlumatları üçün təşkilatınızın administratoru ilə əlaqə saxlayın.",
        ),
    )
    return redirect("accounts:login")


def register_view(request):
    """Start registration by caching the payload and sending a signup OTP."""
    if not _public_signup_enabled():
        return _signup_disabled_redirect(request)
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            pending_registration = None
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
                messages.error(
                    request,
                    pgettext(
                        "accounts.auth.message",
                        "Bu email üçün saatlıq OTP limiti dolub. Bir az sonra yenidən cəhd edin.",
                    ),
                )
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
                if pending_registration:
                    clear_pending_registration(pending_registration["email"])
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
    if not _public_signup_enabled():
        return _signup_disabled_redirect(request)
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
                messages.error(
                    request,
                    pgettext(
                        "accounts.auth.message",
                        "OTP təsdiqləndi, amma hesab yaradılarkən xəta baş verdi. Yenidən cəhd edin.",
                    ),
                )
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
        messages.error(
            request,
            pgettext("accounts.auth.message", "Yeni OTP kodu üçün {seconds} saniyə gözləyin.").format(
                seconds=exc.retry_after
            ),
        )
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
        messages.error(
            request,
            pgettext(
                "accounts.auth.message",
                "Bu email üçün saatlıq OTP limiti dolub. Bir az sonra yenidən cəhd edin.",
            ),
        )
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


def logout_view(request):
    """Logout user and redirect to the login page.

    Only POST requests are accepted to prevent cross-site forced-logout attacks
    (e.g. an attacker embedding ``<img src="/accounts/logout/">`` on another page).
    GET requests receive HTTP 405 Method Not Allowed.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    logout(request)
    messages.success(request, pgettext_lazy("accounts.auth.message", "logout_success"))
    return redirect("accounts:login")
