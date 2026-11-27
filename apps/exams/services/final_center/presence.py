"""final_center paketi — efemer presence (Redis cache) qatı.

Heartbeat-lər DB-yə YAZILMIR — hər biletin canlı vəziyyəti TTL-li cache
açarında saxlanır (multi-instance mühitdə paylaşılan Redis). DB-də yalnız
dövri, seyrək snapshot sahələri (``last_seen_at``, ``reconnect_count``)
yenilənir.

Hər biletin bağlantıları ayrı vaxt nişanları ilə saxlanır.
"""

from datetime import timedelta
from threading import Lock

from django.core.cache import cache, caches
from django.core.cache.backends.redis import RedisCache
from django.utils import timezone

# Heartbeat intervalı client-də ~30s; TTL 3 interval — qısa şəbəkə
# fasilələrində presence itmir, amma ölü bağlantı 90s-ə təmizlənir.
PRESENCE_TTL_SECONDS = 90
HEARTBEAT_INTERVAL_SECONDS = 30

# ``last_seen_at``-ın DB-yə yazılma seyrəkliyi (saniyə) — hər heartbeat-də yox.
_DB_TOUCH_MIN_INTERVAL = 120


def _key(session_id: int, ticket_id: int) -> str:
    return f"finpr:{session_id}:{ticket_id}"


_LOCAL_LOCK = Lock()
_LEGACY_CONNECTION = "legacy"


def _live_connections(value, now):
    if not value:
        return {}
    # Existing cache entries from the previous deployment expire normally.
    connections = {_LEGACY_CONNECTION: value} if "ts" in value else value
    cutoff = (now - timedelta(seconds=PRESENCE_TTL_SECONDS)).isoformat()
    return {name: seen for name, seen in connections.items() if seen["ts"] > cutoff}


def _update(session_id, ticket_id, connection_id, status):
    key = _key(session_id, ticket_id)

    def change(value):
        now = timezone.now()
        live = _live_connections(value, now)
        if status is not None:
            live[connection_id] = {"ts": now.isoformat(), "st": status}
            return live, False
        if connection_id is None:
            return {}, bool(live)
        removed = live.pop(connection_id, None)
        return live, removed is not None and not live

    backend = caches["default"]
    if isinstance(backend, RedisCache):
        # WATCH retries when another ASGI process updates this ticket. All reads and commits use the primary.
        redis_key = backend.make_and_validate_key(key)
        client = backend._cache.get_client(redis_key, write=True)
        serializer = backend._cache._serializer

        def update_watched(pipe):
            raw = pipe.get(redis_key)
            live, last_closed = change(serializer.loads(raw) if raw is not None else None)
            pipe.multi()
            if live:
                pipe.set(redis_key, serializer.dumps(live), ex=PRESENCE_TTL_SECONDS)
            else:
                pipe.delete(redis_key)
            return last_closed

        return client.transaction(update_watched, redis_key, value_from_callable=True)
    # The development/test cache is process-local.
    with _LOCAL_LOCK:
        live, last_closed = change(cache.get(key))
        if live:
            cache.set(key, live, PRESENCE_TTL_SECONDS)
        else:
            cache.delete(key)
        return last_closed


def touch_presence(session_id, ticket_id, *, status="waiting", connection_id=_LEGACY_CONNECTION):
    _update(session_id, ticket_id, connection_id, status)


def drop_presence(session_id, ticket_id, *, connection_id=None):
    """Return true only for the removal of the final live connection. Ticket revocation clears all."""
    return _update(session_id, ticket_id, connection_id, None)


def presence_map(session_id: int, ticket_ids) -> dict:
    """Return the most recent live heartbeat per ticket in a single cache read."""
    keys = {_key(session_id, tid): tid for tid in ticket_ids}
    if not keys:
        return {}
    now = timezone.now()
    result = {}
    for key, value in cache.get_many(keys).items():
        live = _live_connections(value, now)
        if live:
            result[keys[key]] = max(live.values(), key=lambda seen: seen["ts"])
    return result


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
