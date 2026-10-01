"""Proktorinq skriptinin «canlılıq» siqnalı (heartbeat) — DB-yə YAZILMIR.

Tələbə səhifəsindəki nəzarət skripti ~30 s-dən bir kiçik POST göndərir; son
vəziyyət TTL-li cache açarında saxlanılır (``final_center.presence`` ilə eyni
yanaşma). Monitor bu açarları ``get_many`` ilə TƏK çağırışda oxuyur:

* heartbeat köhnəlib → «Nəzarət siqnalı kəsilib» (skript söndürülüb, səhifə
  bağlanıb, brauzer genişlənməsi sorğuları bloklayır, şəbəkə kəsilib …);
* heartbeat heç gəlməyib → «Nəzarət siqnalı yoxdur».

Heç biri avtomatik cəza deyil — nəzarətçiyə baxış üçün göstəricidir. Uzun
fasilədən sonra gələn ilk heartbeat ``heartbeat_gap`` siqnalını ``ProctoringLog``-a
bir dəfə yazır ki, tarixçədə iz qalsın.
"""

from __future__ import annotations

import time

from django.core.cache import caches
from django.core.cache.backends.dummy import DummyCache
from django.core.cache.backends.locmem import LocMemCache

HEARTBEAT_INTERVAL_SECONDS = 30
#: Bu qədər saniyə heartbeat yoxdursa «kəsilib» sayılır (3 interval + ehtiyat).
HEARTBEAT_STALE_SECONDS = 95
#: Cəhd başladıqdan bu qədər sonra hələ heç bir heartbeat yoxdursa «yoxdur».
HEARTBEAT_GRACE_SECONDS = 120
_TTL_SECONDS = 6 * 60 * 60

# Test/dev DummyCache-də vəziyyət itməsin (rate_limit ilə eyni fallback ideyası).
_FALLBACK_CACHE = LocMemCache("ems-proctor-heartbeat", {})

_BOOL_FIELDS = ("fs", "vis", "foc", "ext", "dt")


def _cache():
    cache = caches["default"]
    if isinstance(cache, DummyCache):
        return _FALLBACK_CACHE
    return cache


def _key(attempt_id: int) -> str:
    return f"procbeat:{attempt_id}"


def _clean_state(state) -> dict:
    clean = {}
    if not isinstance(state, dict):
        return clean
    for field in _BOOL_FIELDS:
        value = state.get(field)
        if isinstance(value, bool):
            clean[field] = value
    for field in ("w", "h"):
        value = state.get(field)
        if isinstance(value, int) and not isinstance(value, bool):
            clean[field] = max(0, min(20000, value))
    return clean


def record_heartbeat(attempt_id: int, state=None, *, now: float | None = None) -> dict:
    """Heartbeat-i yazır; ``{"gap_seconds": int|None}`` qaytarır.

    ``gap_seconds`` — əvvəlki heartbeat ``HEARTBEAT_STALE_SECONDS``-dan köhnədirsə
    fasilənin uzunluğu (çağıran onu ``heartbeat_gap`` siqnalı kimi qeyd edir).
    """
    now = time.time() if now is None else now
    payload = _clean_state(state)
    payload["ts"] = now
    gap = None
    try:
        cache = _cache()
        previous = cache.get(_key(attempt_id))
        if isinstance(previous, dict) and isinstance(previous.get("ts"), (int, float)):
            delta = now - previous["ts"]
            if delta > HEARTBEAT_STALE_SECONDS:
                gap = int(delta)
        cache.set(_key(attempt_id), payload, _TTL_SECONDS)
    except Exception:  # noqa: BLE001 — cache nasazlığı imtahanı dayandırmamalıdır
        return {"gap_seconds": None}
    return {"gap_seconds": gap}


def heartbeat_map(attempt_ids) -> dict:
    """{attempt_id: payload} — yalnız heartbeat-i olan cəhdlər (TƏK cache çağırışı)."""
    ids = [attempt_id for attempt_id in set(attempt_ids) if attempt_id]
    if not ids:
        return {}
    keys = {_key(attempt_id): attempt_id for attempt_id in ids}
    try:
        found = _cache().get_many(list(keys))
    except Exception:  # noqa: BLE001
        return {}
    return {keys[key]: value for key, value in found.items() if isinstance(value, dict)}


def heartbeat_state(payload, *, started_at=None, now: float | None = None) -> dict:
    """Monitor üçün: {"age": saniyə|None, "status": "ok"|"stale"|"missing"|"pending"}."""
    now = time.time() if now is None else now
    if isinstance(payload, dict) and isinstance(payload.get("ts"), (int, float)):
        age = max(0, int(now - payload["ts"]))
        return {
            "age": age,
            "status": "stale" if age > HEARTBEAT_STALE_SECONDS else "ok",
            "fullscreen": payload.get("fs"),
            "visible": payload.get("vis"),
            "extended_screen": payload.get("ext"),
        }
    if started_at is not None and now - started_at.timestamp() > HEARTBEAT_GRACE_SECONDS:
        return {"age": None, "status": "missing"}
    return {"age": None, "status": "pending"}


def clear_heartbeat(attempt_id: int) -> None:
    try:
        _cache().delete(_key(attempt_id))
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "HEARTBEAT_GRACE_SECONDS",
    "HEARTBEAT_INTERVAL_SECONDS",
    "HEARTBEAT_STALE_SECONDS",
    "clear_heartbeat",
    "heartbeat_map",
    "heartbeat_state",
    "record_heartbeat",
]
