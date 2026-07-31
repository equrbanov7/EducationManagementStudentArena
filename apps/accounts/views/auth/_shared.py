"""accounts auth view paketi — _shared."""

import json
import secrets

from django.conf import settings
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.core.signing import BadSignature
from django.http import JsonResponse

from apps.accounts.models import EmailOTP
from core.helpers import _safe_same_origin_redirect_path
from core.rate_limit import clear_rate_limit, normalize_rate_identity
from core.utils import get_client_ip

from .constants import (
    AUTH_DEVICE_COOKIE_MAX_AGE,
    AUTH_DEVICE_COOKIE_NAME,
    AUTH_DEVICE_COOKIE_SALT,
    AUTH_DEVICE_ID_RE,
    AUTH_REDIRECT_DISALLOWED_CHARS,
    AUTH_REDIRECT_MAX_LENGTH,
    LOGIN_LIMIT_SCOPE_DEVICE,
    LOGIN_LIMIT_SCOPE_IDENTITY,
)


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
    """Login rate-limit vedrələri: ``(rate_spec, scope, *key_parts)`` siyahısı.

    İKİ QAT:

    * **Cihaz qatı** (`LOGIN_RATE_LIMIT`, dar — 5/10m) — imzalanmış cihaz
      cookie-si üzərində. Universitet NAT-ı arxasındakı istifadəçilər bir-birini
      bloklamasın deyə əsas qat budur.
    * **İP qatı** (`LOGIN_IP_RATE_LIMIT`, geniş — 60/10m) — cookie-dən ASILI
      DEYİL.

    TƏHLÜKƏSİZLİK: yalnız cihaz qatı olsaydı, cookie göndərməyən klient üçün
    ``_get_auth_device_id`` hər sorğuda təzə id yaradırdı → hər cəhd öz
    vedrəsinə düşür və limit heç vaxt işə düşmür (brute-force tam açıq).
    İP qatı bu yolu bağlayır, geniş həddi isə paylaşılan İP-ni qorumaqda davam
    edir.
    """
    device_id = _get_auth_device_id(request)
    normalized_username = normalize_rate_identity(username)
    client_ip = (get_client_ip(request) or "unknown").strip().lower()
    ip_key = f"ip:{client_ip}"
    device_rate = settings.LOGIN_RATE_LIMIT
    ip_rate = getattr(settings, "LOGIN_IP_RATE_LIMIT", device_rate)
    return [
        # Dar: cihaz cookie-si (mövcud davranış — paylaşılan İP-də izolyasiya).
        (device_rate, LOGIN_LIMIT_SCOPE_DEVICE, device_id),
        (device_rate, LOGIN_LIMIT_SCOPE_IDENTITY, device_id, normalized_username),
        # Geniş: cookie-siz hücumu dayandıran İP qapısı.
        (ip_rate, LOGIN_LIMIT_SCOPE_DEVICE, ip_key),
        (ip_rate, LOGIN_LIMIT_SCOPE_IDENTITY, ip_key, normalized_username),
    ]


def _clear_login_rate_limits_after_password_reset(request, user):
    """Parol sıfırlandıqdan sonra hər iki açar ailəsini (İP + cihaz) təmizlə.

    ``_login_limit_keys`` ilə simmetrik olmalıdır, əks halda istifadəçi parolu
    sıfırlasa belə İP vedrəsi dolu qalıb girişi bloklayardı.
    """
    device_id = _get_auth_device_id(request)
    client_ip = (get_client_ip(request) or "unknown").strip().lower()
    ip_key = f"ip:{client_ip}"

    clear_rate_limit(LOGIN_LIMIT_SCOPE_DEVICE, ip_key)
    clear_rate_limit(LOGIN_LIMIT_SCOPE_DEVICE, device_id)

    identities = {
        getattr(user, "username", ""),
        getattr(user, "email", ""),
    }
    for identity in identities:
        if identity:
            normalized = normalize_rate_identity(identity)
            clear_rate_limit(LOGIN_LIMIT_SCOPE_IDENTITY, ip_key, normalized)
            clear_rate_limit(LOGIN_LIMIT_SCOPE_IDENTITY, device_id, normalized)


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

    # Final imtahan girişi ayrıca kiosk/PIN axınıdır. Normal kabinet login
    # formaları heç vaxt login sonrası istifadəçini ora aparmamalıdır.
    normalized_path = (safe_path.split("?", 1)[0] or "/").rstrip("/") + "/"
    if normalized_path == "/exams/final/":
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
