"""final_center paketi — efemer presence (Redis cache) qatı.

Heartbeat-lər DB-yə YAZILMIR — hər biletin canlı vəziyyəti TTL-li cache
açarında saxlanır (multi-instance mühitdə paylaşılan Redis). DB-də yalnız
dövri, seyrək snapshot sahələri (``last_seen_at``, ``reconnect_count``)
yenilənir.

Açar sxemi: ``finpr:{session_id}:{ticket_id}`` → {"ts": iso, "st": status}.
"""

from django.core.cache import cache
from django.utils import timezone

# Heartbeat intervalı client-də ~30s; TTL 3 interval — qısa şəbəkə
# fasilələrində presence itmir, amma ölü bağlantı 90s-ə təmizlənir.
PRESENCE_TTL_SECONDS = 90
HEARTBEAT_INTERVAL_SECONDS = 30

# ``last_seen_at``-ın DB-yə yazılma seyrəkliyi (saniyə) — hər heartbeat-də yox.
_DB_TOUCH_MIN_INTERVAL = 120


def _key(session_id: int, ticket_id: int) -> str:
    return f"finpr:{session_id}:{ticket_id}"


def touch_presence(session_id: int, ticket_id: int, *, status: str = "waiting") -> None:
    cache.set(
        _key(session_id, ticket_id),
        {"ts": timezone.now().isoformat(), "st": status},
        PRESENCE_TTL_SECONDS,
    )


def drop_presence(session_id: int, ticket_id: int) -> None:
    cache.delete(_key(session_id, ticket_id))


def presence_map(session_id: int, ticket_ids) -> dict:
    """{ticket_id: payload} — yalnız hazırda canlı görünən biletlər."""
    ids = list(ticket_ids)
    if not ids:
        return {}
    keys = {_key(session_id, tid): tid for tid in ids}
    found = cache.get_many(list(keys.keys()))
    return {keys[k]: v for k, v in found.items()}


def connected_count(session_id: int, ticket_ids) -> int:
    return len(presence_map(session_id, ticket_ids))


def touch_ticket_last_seen(ticket) -> None:
    """DB-yə seyrək yazılan ``last_seen_at`` — heartbeat başına sətir YOX."""
    now = timezone.now()
    last = ticket.last_seen_at
    if last is not None and (now - last).total_seconds() < _DB_TOUCH_MIN_INTERVAL:
        return
    type(ticket).objects.filter(pk=ticket.pk).update(last_seen_at=now)


__all__ = [
    "HEARTBEAT_INTERVAL_SECONDS",
    "PRESENCE_TTL_SECONDS",
    "connected_count",
    "drop_presence",
    "presence_map",
    "touch_presence",
    "touch_ticket_last_seen",
]
