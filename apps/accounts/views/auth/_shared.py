"""accounts auth view paketi — _shared."""

import hashlib
import logging
import secrets

from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.core.signing import BadSignature

from apps.accounts.identity import login_rate_identity
from apps.accounts.models import EmailOTP
from core import runtime_settings
from core.helpers import _safe_same_origin_redirect_path
from core.rate_limit import clear_rate_limit, is_rate_limited, normalize_rate_identity, record_rate_limit_hit
from core.utils import get_client_ip

from .constants import (
    AUTH_DEVICE_COOKIE_MAX_AGE,
    AUTH_DEVICE_COOKIE_NAME,
    AUTH_DEVICE_COOKIE_SALT,
    AUTH_DEVICE_ID_RE,
    AUTH_REDIRECT_DISALLOWED_CHARS,
    AUTH_REDIRECT_MAX_LENGTH,
    LOGIN_ACCOUNT_DISTINCT_IP_ALERT_DEFAULT,
    LOGIN_ACCOUNT_IP_TRACK_SECONDS,
    LOGIN_ACCOUNT_RATE_LIMIT_DEFAULT,
    LOGIN_LIMIT_SCOPE_ACCOUNT,
    LOGIN_LIMIT_SCOPE_DEVICE,
    LOGIN_LIMIT_SCOPE_IDENTITY,
    LOGIN_LIMIT_SCOPE_SUPERADMIN_ESCAPE,
    LOGIN_SUPERADMIN_ESCAPE_RATE_LIMIT_DEFAULT,
)

logger = logging.getLogger(__name__)


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

    Audit 2026-09-28 SA-03: üçüncü, **hesab qatı** (`LOGIN_ACCOUNT_RATE_LIMIT`,
    yumşaq — 20/1h) yalnız normalizə olunmuş istifadəçi adına bağlıdır. Hər
    cəhdi fərqli İP-dən (cookie-siz) göndərən paylanmış hücum əvvəlki iki qatı
    keçirdi; indi bir hesab üçün saatda ən çox 20 uğursuz cəhd mümkündür.
    """
    device_id = _get_auth_device_id(request)
    normalized_username = login_rate_identity(username)
    client_ip = (get_client_ip(request) or "unknown").strip().lower()
    ip_key = f"ip:{client_ip}"
    # 2026-10-03: limitlər «Sistem tənzimləmələri»ndən (RİM rəhbəri dəyişir); yoxdursa mühitin defoltu.
    device_rate = runtime_settings.get("login.device_rate")
    ip_rate = runtime_settings.get("login.ip_rate")
    return [
        # Dar: cihaz cookie-si (mövcud davranış — paylaşılan İP-də izolyasiya).
        (device_rate, LOGIN_LIMIT_SCOPE_DEVICE, device_id),
        (device_rate, LOGIN_LIMIT_SCOPE_IDENTITY, device_id, normalized_username),
        # Geniş: cookie-siz hücumu dayandıran İP qapısı.
        (ip_rate, LOGIN_LIMIT_SCOPE_DEVICE, ip_key),
        (ip_rate, LOGIN_LIMIT_SCOPE_IDENTITY, ip_key, normalized_username),
        # Yumşaq: yalnız hesab (SA-03) — paylanmış təxminə qarşı.
        (_login_account_rate_limit(), LOGIN_LIMIT_SCOPE_ACCOUNT, normalized_username),
    ]


def _login_account_rate_limit():
    return runtime_settings.get("login.account_rate") or LOGIN_ACCOUNT_RATE_LIMIT_DEFAULT


def _note_failed_login_ip(request, username):
    """Audit 2026-09-28 SA-03: bir hesab üçün uğursuz cəhd edən fərqli İP-ləri say.

    Say ``LOGIN_ACCOUNT_DISTINCT_IP_ALERT`` həddinə çatanda (pəncərə ərzində bir
    dəfə) WARNING yazılır — paylanmış parol təxmininin siqnalı. İP-lər xam deyil,
    heş kimi saxlanılır; keş xətası login-i heç vaxt sındırmır.
    """
    threshold = int(getattr(settings, "LOGIN_ACCOUNT_DISTINCT_IP_ALERT", LOGIN_ACCOUNT_DISTINCT_IP_ALERT_DEFAULT))
    if threshold <= 0:
        return
    normalized_username = login_rate_identity(username)
    digest = hashlib.sha256(normalized_username.encode("utf-8")).hexdigest()
    ip_digest = hashlib.sha256(_client_ip_key(request).encode("utf-8")).hexdigest()[:16]
    track_key = f"accounts.login.account_ips:{digest}"
    alert_key = f"{track_key}:alerted"
    try:
        cache = caches[getattr(settings, "RATELIMIT_USE_CACHE", "default")]
        seen = list(cache.get(track_key) or [])
        if ip_digest in seen:
            return
        seen = (seen + [ip_digest])[-(threshold + 1) :]
        cache.set(track_key, seen, timeout=LOGIN_ACCOUNT_IP_TRACK_SECONDS)
        if len(seen) >= threshold and cache.add(alert_key, 1, timeout=LOGIN_ACCOUNT_IP_TRACK_SECONDS):
            logger.warning(
                "Distributed login failures: %s distinct IPs failed for one account within %s s",
                len(seen),
                LOGIN_ACCOUNT_IP_TRACK_SECONDS,
                extra={"username_hash": digest[:16], "distinct_ips": len(seen)},
            )
    except Exception:  # noqa: BLE001 — siqnal login axınını sındırmamalıdır.
        logger.debug("Failed-login IP tracking skipped", exc_info=True)


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
            normalized = login_rate_identity(identity)
            clear_rate_limit(LOGIN_LIMIT_SCOPE_IDENTITY, ip_key, normalized)
            clear_rate_limit(LOGIN_LIMIT_SCOPE_IDENTITY, device_id, normalized)
            clear_rate_limit(LOGIN_LIMIT_SCOPE_ACCOUNT, normalized)


def _client_ip_key(request):
    client_ip = (get_client_ip(request) or "unknown").strip().lower()
    return f"ip:{client_ip}"


def _authenticate_superadmin_for_rate_limit_reset(request, username, password):
    if not username or not password:
        return None

    user = authenticate(request=request, username=username, password=password)
    if user is None:
        return None

    if user.is_superuser or getattr(user, "is_superadmin", False):
        return user
    return None


def _superadmin_escape_under_login_limit(request, username, password, limit_keys):
    """Login limiti DOLANDA superadmin qaçış yolu — dar, ayrıca vedrə ilə.

    2026-09-13 access auditi, F-01 (P1). Qaçış yolu NİYƏ var: hücumçu superadmin
    adına səhv cəhdlərlə normal vedrəni doldurub yeganə bərpa hesabını
    kilidləyə bilməməlidir (kilid = DoS; superadmin üçün «parolu sıfırla»
    yolu da yoxdur). NİYƏ təhlükəli idi: limit dolandan sonra hər cəhd yenə
    ``authenticate()``-dən keçirdi və heç yerdə sayılmırdı — superadmin (ən
    dəyərli hesab) üçün brute-force faktiki sərhədsiz idi (auditor zondu
    ``A3-superadmin-correct-under-limit`` → 302 + sessiya).

    İndi:
    * hər parol yoxlaması ``accounts.login.superadmin_escape`` vedrəsindən
      (İP + istifadəçi adı, default 3/1h) bir token xərcləyir — vedrə dolubsa
      parol HEÇ yoxlanmır;
    * uğursuz cəhd normal login vedrələrində də sayılır (əvvəl sayılmırdı);
    * yalnız superadmin hesabı üçün düzgün parol qaçışa icazə verir.
    """
    escape_rate = getattr(settings, "LOGIN_SUPERADMIN_ESCAPE_RATE_LIMIT", LOGIN_SUPERADMIN_ESCAPE_RATE_LIMIT_DEFAULT)
    escape_key = (_client_ip_key(request), login_rate_identity(username))
    escape_limited, _retry_after = is_rate_limited(LOGIN_LIMIT_SCOPE_SUPERADMIN_ESCAPE, escape_rate, *escape_key)
    if escape_limited:
        return None

    record_rate_limit_hit(LOGIN_LIMIT_SCOPE_SUPERADMIN_ESCAPE, escape_rate, *escape_key)
    user = _authenticate_superadmin_for_rate_limit_reset(request, username, password)
    if user is None:
        for rate_spec, scope, *key_parts in limit_keys:
            record_rate_limit_hit(scope, rate_spec, *key_parts)
    return user


def _ip_rate_limited_and_recorded(request, scope, rate):
    """İP vedrəsini yoxla; dolmayıbsa cəhdi say. ``(limited, retry_after)`` qaytarır.

    2026-09-13 access auditi, F-09: OTP JSON endpoint-ləri və parol-bərpa
    formaları üçün e-poçtdan ASILI OLMAYAN İP qapısı. Hər POST — nəticəsindən
    asılı olmayaraq — sayılır, çünki məqsəd fərqli e-poçtlara «spray»-i
    dayandırmaqdır; e-poçt üzrə hədlər (saatlıq 5, OTP başına 5 cəhd) qalır.
    """
    ip_key = _client_ip_key(request)
    limited, retry_after = is_rate_limited(scope, rate, ip_key)
    if limited:
        return True, retry_after
    record_rate_limit_hit(scope, rate, ip_key)
    return False, None


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


def _validate_otp_email(value):
    email = EmailOTP.normalize_email(value)
    if not email or "@" not in email:
        raise ValidationError("Etibarlı email ünvanı daxil edin.")
    return email
