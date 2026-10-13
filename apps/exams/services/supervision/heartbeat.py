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

import re
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


#: Bir səhifə yükləməsinin təsadüfi id-si (``proctor_signals.js``) — yalnız bu format qəbul olunur.
_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,40}$")
#: İki səhifənin «eyni anda canlı» sayılması üçün maks. fasilə (2 interval + ehtiyat).
CONCURRENT_WINDOW_SECONDS = 2 * HEARTBEAT_INTERVAL_SECONDS + 10
#: Yaddaşda saxlanan son səhifə id-ləri (köhnələri atılır).
_MAX_PEERS = 4
_PEER_TTL_SECONDS = 10 * 60


def _clean_client_id(value):
    if isinstance(value, str) and _CLIENT_ID_RE.match(value):
        return value
    return None


def _concurrent_peer(peers: dict, client_id: str, now: float) -> bool:
    """Bu səhifənin ƏVVƏLKİ heartbeat-indən sonra BAŞQA səhifə də heartbeat göndəribmi?

    Səhv-müsbətdən qorunma (2026-10-13, gecə): səhifəni yeniləmək (reload) yeni id
    yaradır, köhnə id isə bir daha göndərmir — «növbələşmə» (A → B → A) yalnız iki
    səhifə EYNİ ANDA açıq olanda baş verir (iki cihaz və ya iki tab).
    """
    previous_self = peers.get(client_id)
    if previous_self is None:
        return False
    for other, ts in peers.items():
        if other == client_id or not isinstance(ts, (int, float)):
            continue
        if ts > previous_self and now - ts <= CONCURRENT_WINDOW_SECONDS:
            return True
    return False


def record_heartbeat(attempt_id: int, state=None, *, now: float | None = None, ip: str | None = None) -> dict:
    """Heartbeat-i yazır; ``{"gap_seconds", "concurrent", "ip_change"}`` qaytarır.

    * ``gap_seconds`` — əvvəlki heartbeat ``HEARTBEAT_STALE_SECONDS``-dan köhnədirsə
      fasilənin uzunluğu (çağıran onu ``heartbeat_gap`` siqnalı kimi qeyd edir);
    * ``concurrent`` — eyni cəhd iki canlı səhifədən gəlir (``state.cid`` növbələşməsi);
    * ``ip_change`` — ``(köhnə, yeni)`` IP cütü, cəhd ortasında dəyişibsə.
    """
    now = time.time() if now is None else now
    raw_state = state if isinstance(state, dict) else {}
    payload = _clean_state(raw_state)
    payload["ts"] = now
    client_id = _clean_client_id(raw_state.get("cid"))
    result = {"gap_seconds": None, "concurrent": False, "ip_change": None}
    try:
        cache = _cache()
        previous = cache.get(_key(attempt_id))
        previous = previous if isinstance(previous, dict) else {}
        if isinstance(previous.get("ts"), (int, float)):
            delta = now - previous["ts"]
            if delta > HEARTBEAT_STALE_SECONDS:
                result["gap_seconds"] = int(delta)
        peers = previous.get("peers") if isinstance(previous.get("peers"), dict) else {}
        peers = {k: v for k, v in peers.items() if isinstance(v, (int, float)) and now - v <= _PEER_TTL_SECONDS}
        if client_id:
            result["concurrent"] = _concurrent_peer(peers, client_id, now)
            peers[client_id] = now
            if len(peers) > _MAX_PEERS:
                peers = dict(sorted(peers.items(), key=lambda item: item[1], reverse=True)[:_MAX_PEERS])
        payload["peers"] = peers
        previous_ip = previous.get("ip") if isinstance(previous.get("ip"), str) else None
        if ip:
            ip = str(ip)[:45]
            if previous_ip and previous_ip != ip:
                result["ip_change"] = (previous_ip, ip)
            payload["ip"] = ip
        elif previous_ip:
            payload["ip"] = previous_ip
        cache.set(_key(attempt_id), payload, _TTL_SECONDS)
    except Exception:  # noqa: BLE001 — cache nasazlığı imtahanı dayandırmamalıdır
        return {"gap_seconds": None, "concurrent": False, "ip_change": None}
    return result


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
    "CONCURRENT_WINDOW_SECONDS",
    "clear_heartbeat",
    "heartbeat_map",
    "heartbeat_state",
    "record_heartbeat",
]
