"""accounts auth view paketi — _shared."""

import json
import secrets

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
