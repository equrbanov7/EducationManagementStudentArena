"""accounts auth view paketi — otp_api."""

from django.conf import settings
from django.contrib.auth import login
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.accounts.identity import user_access_is_login_blocked
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
    _ip_rate_limited_and_recorded,
    _json_error,
    _load_request_payload,
    _resolve_otp_purpose,
    _validate_otp_email,
)
from .constants import (
    OTP_SEND_IP_LIMIT_SCOPE,
    OTP_VERIFY_IP_LIMIT_SCOPE,
    User,
    otp_send_ip_rate_limit,
    otp_verify_ip_rate_limit,
)

_NEUTRAL_SENT_DETAIL = "Əgər bu email qeydiyyatdan keçibsə, OTP göndərildi."


def _public_signup_enabled():
    return bool(getattr(settings, "PUBLIC_SIGNUP_ENABLED", False))


def _neutral_sent_response():
    """Hesab mövcudluğunu sızdırmayan 202 (mövcud/naməlum/bloklu üçün EYNİ)."""
    return JsonResponse({"success": True, "detail": _NEUTRAL_SENT_DETAIL}, status=202)


def _ip_limited_json(request, scope, rate):
    """F-09 (2026-09-13): İP qapısı dolubsa 429 JSON, əks halda ``None``."""
    limited, retry_after = _ip_rate_limited_and_recorded(request, scope, rate)
    if limited:
        return _json_error(
            "Çox sayda cəhd edildi. Bir az sonra yenidən cəhd edin.", status=429, retry_after=retry_after
        )
    return None


def _send_with_cooldown_errors(send_callable, *, cooldown_detail):
    """OTP göndərişini icra et; cooldown/saatlıq hədd xətalarını 429 JSON-a çevir."""
    try:
        send_callable()
    except OTPResendCooldownError as exc:
        return _json_error(
            cooldown_detail,
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
    return None


def _neutral_purpose_send_callable(purpose, email, user, request):
    """``login`` / ``password_reset`` üçün göndəriş; uyğun hədəf yoxdursa ``None``.

    F-02 (2026-09-13): ``password_reset`` məqsədi əvvəl ümumi budağa düşürdü —
    mövcud→202, naməlum→404 (aydın hesab orakulu) və üstəlik SIGNUP OTP-si
    göndərirdi (yoxlama isə PASSWORD_RESET məqsədini axtarırdı — heç vaxt
    uyğun gəlmirdi). İndi ``login`` kimi NEYTRALDIR: uyğun hesab yoxdursa da
    eyni 202 qaytarılır; hesab varsa məqsədə uyğun OTP göndərilir.
    """
    if user is None or not user.is_active or user_access_is_login_blocked(user):
        return None
    if purpose == EmailOTP.Purpose.LOGIN:
        return lambda: send_login_otp(email, request=request, user=user, enforce_cooldown=True)
    return lambda: send_otp_email(email, user=user, purpose=purpose, request=request, enforce_cooldown=True)


def _signup_send_callable(email, user, pending_registration, request):
    """``signup`` üçün göndəriş və ya (xəta cavabı, ``None``) cütü.

    F-02 (2026-09-13): 404 («istifadəçi tapılmadı») / 409 («artıq təsdiqlənib»)
    cavabları hesab mövcudluğunu sızdırır. Açıq qeydiyyat SÖNÜLÜDÜRSƏ (prod
    default, e-universitet təminat modeli) bu fərq artıq heç kimə lazım deyil —
    hər hal üçün neytral 202 qaytarılır, göndəriş yalnız real hədəf (təsdiqsiz
    hesab / gözləyən qeydiyyat) varsa baş verir. Açıq qeydiyyat AÇIQ olanda
    qeydiyyat UI-ının ehtiyac duyduğu 404/409 saxlanılır.
    """
    neutral = not _public_signup_enabled()
    if user is not None and user_access_is_login_blocked(user):
        return (None if neutral else _json_error("Bu email üçün istifadəçi tapılmadı.", status=404)), None
    if user is None and not pending_registration:
        return (None if neutral else _json_error("Bu email üçün istifadəçi tapılmadı.", status=404)), None
    if user is not None and user.is_active:
        return (None if neutral else _json_error("Bu email artıq təsdiqlənib.", status=409)), None
    if user is not None:
        return None, lambda: send_verification_otp(user, request=request, enforce_cooldown=True)
    return None, lambda: send_otp_email(email, purpose=EmailOTP.Purpose.SIGNUP, request=request, enforce_cooldown=True)


def _send_otp_common(request, *, cooldown_detail, sent_detail):
    """``send`` və ``resend`` endpoint-lərinin ortaq gövdəsi (fərq yalnız mətnlərdədir)."""
    payload = _load_request_payload(request)
    purpose = _resolve_otp_purpose(payload.get("purpose"), default=EmailOTP.Purpose.LOGIN)

    try:
        email = _validate_otp_email(payload.get("email", ""))
    except ValidationError as exc:
        return _json_error(str(exc.messages[0]))

    limited_response = _ip_limited_json(request, OTP_SEND_IP_LIMIT_SCOPE, otp_send_ip_rate_limit())
    if limited_response is not None:
        return limited_response

    user = User.objects.filter(email__iexact=email).first()

    # Cavab gövdəsi də neytral olan hallar: ``password_reset`` (ayrıca UI yoxdur)
    # və açıq qeydiyyat sönülü olanda ``signup``. ``login`` üçün mövcud müqavilə
    # (göndəriləndə ``expires_in`` ilə fərqli mətn, cooldown-da 429) saxlanılır —
    # ön tərəf geri sayım üçün ona bağlıdır.
    fully_neutral = purpose == EmailOTP.Purpose.PASSWORD_RESET or (
        purpose == EmailOTP.Purpose.SIGNUP and not _public_signup_enabled()
    )

    if purpose == EmailOTP.Purpose.SIGNUP:
        error_response, send_callable = _signup_send_callable(email, user, get_pending_registration(email), request)
        if error_response is not None:
            return error_response
        if send_callable is None:
            return _neutral_sent_response()
    else:
        send_callable = _neutral_purpose_send_callable(purpose, email, user, request)
        if send_callable is None:
            return _neutral_sent_response()

    error_response = _send_with_cooldown_errors(send_callable, cooldown_detail=cooldown_detail)
    if error_response is not None:
        # Neytral məqsədlərdə cooldown/saatlıq hədd də sızdırılmır — göndəriş
        # sadəcə baş vermir (HTML parol-bərpa forması ilə eyni davranış).
        return _neutral_sent_response() if fully_neutral else error_response

    if fully_neutral:
        return _neutral_sent_response()
    return JsonResponse(
        {"success": True, "detail": sent_detail, "expires_in": settings.AUTH_OTP_EXPIRY_SECONDS},
        status=202,
    )


@require_POST
def send_otp_api_view(request):
    """JSON endpoint to issue login/signup OTP emails without exposing the OTP code."""

    return _send_otp_common(
        request,
        cooldown_detail="Yeni OTP kodu üçün bir az gözləyin.",
        sent_detail="OTP emailə göndərildi.",
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

    limited_response = _ip_limited_json(request, OTP_VERIFY_IP_LIMIT_SCOPE, otp_verify_ip_rate_limit())
    if limited_response is not None:
        return limited_response

    code = str(payload.get("otp", "")).strip()
    user = User.objects.filter(email__iexact=email).first()
    pending_registration = get_pending_registration(email)

    # F-02 (2026-09-13): açıq qeydiyyat sönülüdürsə 404/409 ön-yoxlamaları
    # atlanır — naməlum/təsdiqlənmiş e-poçt üçün cavab adi «OTP yanlışdır» 400
    # olur (uyğun gözləyən OTP onsuz da yoxdur), yəni orakul qalmır.
    if purpose == EmailOTP.Purpose.SIGNUP and _public_signup_enabled():
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

    if (
        purpose == EmailOTP.Purpose.LOGIN
        and user is not None
        and user.is_active
        and not user_access_is_login_blocked(user)
    ):
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
                purpose == EmailOTP.Purpose.LOGIN and user and user.is_active and not user_access_is_login_blocked(user)
            ),
        }
    )


@require_POST
def resend_otp_api_view(request):
    """JSON endpoint to resend an OTP after the cooldown window."""

    return _send_otp_common(
        request,
        cooldown_detail="Resend üçün gözləmə vaxtı hələ bitməyib.",
        sent_detail="Yeni OTP göndərildi.",
    )
