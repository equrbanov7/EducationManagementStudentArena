"""final_center paketi — zal monitoru snapshot-unun qısa keşi + ETag (2026-10-13, gecə).

Problem: hər nəzarətçi/mərkəz ekranı ``room_monitor_snapshot``-u 10 s-dən bir çəkir;
snapshot ~10 sorğu + tənbəl yazılar (bilet sinxronu, vaxtı bitmiş cəhdin bağlanması)
edir. Bir zala 3–5 ekran baxanda eyni iş 3–5 dəfə təkrarlanırdı, 300 tələbəlik
sessiyada hər cavab ~150–250 KB JSON idi və planşet hər 10 s bütün xəritəni
yenidən çəkirdi.

Həll:

* **Paylaşılan mikro-keş** (``SNAPSHOT_CACHE_SECONDS``): snapshot istifadəçidən asılı
  deyil (icazə view-da yoxlanır, snapshot yalnız zalın məlumatıdır), ona görə bir zal
  üçün bir hesablama bütün ekranlara xidmət edir — yük ekran sayından asılı olmur.
* **ETag / If-None-Match**: imza dəyişkən sahələr (``server_now``,
  ``remaining_seconds``, heartbeat ``age``) ÇIXARILMAQLA hesablanır; dəyişiklik
  yoxdursa 304 — gövdə yox, klient JSON parse/render etmir.
* ``fresh=True`` — nəzarətçinin öz əməlindən (başlat/bitir) dərhal sonra keşi keçir və
  yeni nəticəni keşə yazır (digər ekranlar da qazanır).
"""

from __future__ import annotations

import hashlib
import json

from django.core.cache import caches
from django.core.serializers.json import DjangoJSONEncoder

from .monitor import room_monitor_snapshot

SNAPSHOT_CACHE_SECONDS = 3
_VOLATILE_ROW_FIELDS = ("remaining_seconds",)


def _key(room_id) -> str:
    return f"fxc:roomsnap:{room_id}"


def _stable_view(snapshot: dict) -> dict:
    """İmza üçün: zamanla öz-özünə dəyişən sahələr atılır (məzmun eyni qalırsa ETag da eyni)."""
    stable = {key: value for key, value in snapshot.items() if key != "server_now"}
    students = []
    for row in snapshot.get("students") or []:
        clean = {key: value for key, value in row.items() if key not in _VOLATILE_ROW_FIELDS}
        heartbeat = clean.get("heartbeat")
        if isinstance(heartbeat, dict):
            clean["heartbeat"] = {key: value for key, value in heartbeat.items() if key != "age"}
        students.append(clean)
    stable["students"] = students
    return stable


def snapshot_etag(snapshot: dict) -> str:
    raw = json.dumps(_stable_view(snapshot), sort_keys=True, cls=DjangoJSONEncoder, default=str)
    return 'W/"' + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32] + '"'


def cached_room_snapshot(room, *, fresh: bool = False) -> tuple[dict, str]:
    """(snapshot, etag) — keşdən və ya yenidən hesablanmış. Keş nasazlığı → birbaşa hesab."""
    cache = caches["default"]
    key = _key(room.pk)
    if not fresh:
        try:
            hit = cache.get(key)
        except Exception:  # noqa: BLE001 — keş monitoru dayandırmamalıdır
            hit = None
        if isinstance(hit, dict) and "snapshot" in hit and "etag" in hit:
            return hit["snapshot"], hit["etag"]
    snapshot = room_monitor_snapshot(room)
    etag = snapshot_etag(snapshot)
    try:
        cache.set(key, {"snapshot": snapshot, "etag": etag}, SNAPSHOT_CACHE_SECONDS)
    except Exception:  # noqa: BLE001
        pass
    return snapshot, etag


def invalidate_room_snapshot(room_id) -> None:
    try:
        caches["default"].delete(_key(room_id))
    except Exception:  # noqa: BLE001
        pass


def etag_matches(request, etag: str) -> bool:
    header = request.META.get("HTTP_IF_NONE_MATCH") or ""
    if not header or not etag:
        return False
    candidates = {part.strip() for part in header.split(",")}
    return etag in candidates or "*" in candidates


__all__ = [
    "SNAPSHOT_CACHE_SECONDS",
    "cached_room_snapshot",
    "etag_matches",
    "invalidate_room_snapshot",
    "snapshot_etag",
]
