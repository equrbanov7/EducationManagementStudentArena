"""
Cache-backed rate limiting helpers.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.dummy import DummyCache
from django.core.cache.backends.locmem import LocMemCache

_RATE_RE = re.compile(
    r"^\s*(?P<count>\d+)\s*/\s*(?:(?P<window>\d+)\s*(?P<unit>[smhd])|(?P<short_unit>[smhd]))\s*$",
    re.IGNORECASE,
)
_WINDOW_MULTIPLIERS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 60 * 60 * 24,
}
_RATE_LIMIT_FALLBACK_CACHE = LocMemCache("rate-limit-fallback", {})

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedRate:
    limit: int
    window_seconds: int


def parse_rate(rate: str | None) -> ParsedRate | None:
    if not rate:
        return None

    match = _RATE_RE.match(str(rate))
    if not match:
        raise ValueError(f"Unsupported rate limit format: {rate!r}")

    limit = int(match.group("count"))
    unit = (match.group("unit") or match.group("short_unit") or "").lower()
    window_value = int(match.group("window") or 1)
    window_seconds = window_value * _WINDOW_MULTIPLIERS[unit]
    return ParsedRate(limit=limit, window_seconds=window_seconds)


def validate_rate_limit_settings(namespace: dict) -> None:
    """Bütün ``*_RATE_LIMIT`` dəyərlərini parse edir; yararsız varsa ÇÖKÜR.

    2026-09-02 audit, P2-5: səhv yazılmış env dəyəri (məs. ``5/10min``) həmin
    limiteri — LOGIN və OTP daxil — sükutla söndürə bilirdi.  Bu funksiya
    ayarlar YÜKLƏNƏRKƏN çağırılır (``config/settings/components/admin_ratelimit.py``),
    ona görə səhv konfiqurasiya deploy-a keçmir.

    BOŞ dəyər (``""``) QƏSDƏN söndürmə sayılır və buraxılır.
    """
    from django.core.exceptions import ImproperlyConfigured

    problems = []
    for name, value in sorted(namespace.items()):
        if not name.endswith("_RATE_LIMIT") or not isinstance(value, str):
            continue
        try:
            parse_rate(value)
        except ValueError:
            problems.append(f"{name}={value!r}")
    if problems:
        raise ImproperlyConfigured(
            "Yararsız rate-limit konfiqurasiyası (düzgün format: '5/10m', '3/10s', '100/1h'): " + ", ".join(problems)
        )


def normalize_rate_identity(value) -> str:
    return " ".join(str(value or "").strip().lower().split()) or "anonymous"


def _rate_limit_cache():
    cache_alias = getattr(settings, "RATELIMIT_USE_CACHE", "default")
    cache = caches[cache_alias]
    # DummyCache disables persistence entirely, which makes rate-limiting a no-op.
    # Fall back to a process-local cache so throttling still works in test/dev setups.
    if isinstance(cache, DummyCache):
        return _RATE_LIMIT_FALLBACK_CACHE
    return cache


def _cache_keys(scope: str, key_parts: tuple[object, ...]) -> tuple[str, str]:
    raw_key = "|".join(str(part) for part in key_parts if part is not None)
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    base_key = f"ratelimit:{scope}:{digest}"
    return base_key, f"{base_key}:expires"


def _retry_after(cache, expires_key: str, fallback_window: int) -> int:
    expires_at = cache.get(expires_key)
    if expires_at is None:
        return fallback_window
    return max(1, int(expires_at - time.time()))


def _parse_or_fail_closed(scope: str, rate: str | None):
    """Parse edilə bilməyən limit SÜKUTLA söndürmür — LOG + FAIL-CLOSED.

    Konfiqurasiyadan gələn dəyərlər onsuz da proses başlarkən yoxlanılır
    (``config/settings/components/admin_ratelimit.py``), ona görə buraya yalnız
    kodda sərt yazılmış səhv dəyər düşə bilər: onda limit AÇIQ qalmaqdansa
    bağlanır (2026-09-02 audit, P2-5).
    """
    try:
        return parse_rate(rate), False
    except ValueError:
        logger.error("Invalid rate-limit spec %r for scope %r — failing closed.", rate, scope)
        return None, True


def is_rate_limited(scope: str, rate: str | None, *key_parts: object) -> tuple[bool, int | None]:
    if not getattr(settings, "RATELIMIT_ENABLE", True):
        return False, None

    parsed, failed_closed = _parse_or_fail_closed(scope, rate)
    if failed_closed:
        return True, 60
    if parsed is None:
        return False, None

    cache = _rate_limit_cache()
    count_key, expires_key = _cache_keys(scope, key_parts)
    current_count = int(cache.get(count_key) or 0)
    retry_after = _retry_after(cache, expires_key, parsed.window_seconds)
    return current_count >= parsed.limit, retry_after


def record_rate_limit_hit(scope: str, rate: str | None, *key_parts: object) -> tuple[bool, int | None]:
    if not getattr(settings, "RATELIMIT_ENABLE", True):
        return False, None

    parsed, failed_closed = _parse_or_fail_closed(scope, rate)
    if failed_closed:
        return True, 60
    if parsed is None:
        return False, None

    cache = _rate_limit_cache()
    count_key, expires_key = _cache_keys(scope, key_parts)
    now = time.time()

    if cache.add(count_key, 1, timeout=parsed.window_seconds):
        current_count = 1
        cache.set(expires_key, now + parsed.window_seconds, timeout=parsed.window_seconds)
    else:
        try:
            current_count = cache.incr(count_key)
        except ValueError:
            cache.set(count_key, 1, timeout=parsed.window_seconds)
            cache.set(expires_key, now + parsed.window_seconds, timeout=parsed.window_seconds)
            current_count = 1

    retry_after = _retry_after(cache, expires_key, parsed.window_seconds)
    return current_count > parsed.limit, retry_after


def clear_rate_limit(scope: str, *key_parts: object) -> None:
    cache = _rate_limit_cache()
    count_key, expires_key = _cache_keys(scope, key_parts)
    cache.delete_many([count_key, expires_key])
