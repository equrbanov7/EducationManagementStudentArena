"""accounts auth view paketi — otp_api."""

from django.conf import settings
from django.contrib.auth import login
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.accounts.identity import user_access_is_staged
from apps.accounts.models import EmailOTP
from apps.organizations.public import is_tenant_accessible_organization
from core.tenancy import restore_request_organization_from_profile

from ...middleware import POST_LOGIN_REDIRECT_GUARD_SESSION_KEY
from ...services import (
    OTPRateLimitError,
    OTPResendCooldownError,
    activate_user_account,
    finalize_pending_registration,
    get_pending_registration,
    send_login_otp,
    send_otp_email,
    send_verification_otp,
    verify_email_otp,
)
from ._shared import (
    _json_error,
    _load_request_payload,
    _resolve_otp_purpose,
    _validate_otp_email,
)
from .constants import (
    User,
)


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
        if user is None or not user.is_active or user_access_is_staged(user):
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

    if user is not None and user_access_is_staged(user):
        return _json_error("Bu email üçün istifadəçi tapılmadı.", status=404)

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

    if purpose == EmailOTP.Purpose.SIGNUP:
        if user is None and not pending_registration:
            return _json_error("Bu email üçün aktiv qeydiyyat tapılmadı.", status=404)
        if user is not None and user.is_active:
            return _json_error("Bu email artıq təsdiqlənib.", status=409)

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

    if purpose == EmailOTP.Purpose.LOGIN and user is not None and user.is_active and not user_access_is_staged(user):
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
            "authenticated": bool(
                purpose == EmailOTP.Purpose.LOGIN and user and user.is_active and not user_access_is_staged(user)
            ),
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
        if user is None or not user.is_active or user_access_is_staged(user):
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
        if user is not None and user_access_is_staged(user):
            return _json_error("Bu email üçün istifadəçi tapılmadı.", status=404)
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
