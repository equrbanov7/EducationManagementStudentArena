"""Celery/backup sağlamlıq kollektorları.

Problem: Celery worker-ləri ayrıca konteynerlərdədir — onların vəziyyəti app
konteynerinin ``/metrics/`` endpoint-inə birbaşa düşmür (prometheus multiproc
qovluğu konteynerlər arasında paylaşılmır). Həll: beat task-ı statistikanı
Redis cache-ə yazır, app tərəfdə qeydiyyatdan keçən xüsusi kollektor scrape
zamanı cache-dən oxuyub ``emsarena_celery_*`` / ``emsarena_backup_*``
gauge-larını verir. Bununla Prometheus alert-ləri (CeleryWorkersDown,
CeleryBeatStale, BackupTooOld) işləyir.
"""

from __future__ import annotations

import logging
import os
import time

from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "monitoring:celery_stats"
BACKUP_CACHE_KEY = "monitoring:backup_age"
#: Beat intervalından bir qədər uzun TTL — beat dayananda gauge-lar itir və
#: CeleryBeatStale/absent alert-i işə düşür.
CACHE_TTL = 15 * 60

BACKUP_DIR = os.environ.get("MONITORING_BACKUP_DIR", "/backups")

#: 2026-09-13 infra auditi P2-8: ölçülən broker növbələri. Əvvəl yalnız
#: `celery` (defolt) növbəsi `llen` ilə oxunurdu — `heavy` (OCR/AI/export,
#: ayrıca `celery_worker_heavy`) backlog-u və həmin worker-in ölümü heç bir
#: metrikdə görünmürdü. Siyahı `CELERY_TASK_ROUTES`-dakı növbələrlə üst-üstə
#: düşməlidir (config/settings/components/celery_cache.py).
MONITORED_QUEUES: tuple[str, ...] = ("celery", "heavy")


def collect_celery_stats() -> dict:
    """Beat task-ı: worker/queue statistikasını cache-ə yaz (worker prosesində işləyir)."""
    from celery import current_app

    stats: dict = {"collected_at": time.time()}
    try:
        inspect = current_app.control.inspect(timeout=5)
        ping = inspect.ping() or {}
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        scheduled = inspect.scheduled() or {}
        stats["workers_online"] = len(ping)
        stats["active_tasks"] = sum(len(v) for v in active.values())
        stats["reserved_tasks"] = sum(len(v) for v in reserved.values())
        stats["scheduled_tasks"] = sum(len(v) for v in scheduled.values())
        # P2-8: hansı növbəni neçə worker dinləyir — `workers_online` ümumi
        # saydır və heavy worker ölsə (defolt worker sağ qalsa) dəyişmir.
        stats["queue_workers"] = _workers_per_queue(inspect.active_queues() or {})
    except Exception as exc:  # pragma: no cover - broker problemi
        logger.warning("Celery inspect alınmadı: %s", exc)
        stats.update({"workers_online": 0, "active_tasks": 0, "reserved_tasks": 0, "scheduled_tasks": 0})
        stats["queue_workers"] = {queue: 0 for queue in MONITORED_QUEUES}

    # P2-8: hər növbənin uzunluğu ayrıca (`emsarena_celery_queue_length{queue}`).
    # Köhnə skalyar `queue_length` açarı geriyə-uyğunluq üçün defolt növbəyə
    # bərabər saxlanılır (cache-də köhnə formatlı dəyər qalsa kollektor onu da
    # oxuyur).
    stats["queue_lengths"] = _queue_lengths(current_app)
    stats["queue_length"] = stats["queue_lengths"].get("celery", 0)

    cache.set(CACHE_KEY, stats, CACHE_TTL)
    return stats


def _workers_per_queue(active_queues: dict) -> dict[str, int]:
    """`inspect.active_queues()` → {növbə: dinləyən worker sayı} (izlənən növbələr üçün)."""
    counts = {queue: 0 for queue in MONITORED_QUEUES}
    for queues in active_queues.values():
        seen = {item.get("name") for item in (queues or []) if isinstance(item, dict)}
        for queue in seen & set(MONITORED_QUEUES):
            counts[queue] += 1
    return counts


def _queue_lengths(current_app) -> dict[str, int]:
    """Broker-dəki hər izlənən növbənin uzunluğu (Redis `LLEN`); xəta → 0."""
    lengths = {queue: 0 for queue in MONITORED_QUEUES}
    try:
        with current_app.connection_or_acquire() as connection:
            client = connection.default_channel.client
            for queue in MONITORED_QUEUES:
                lengths[queue] = int(client.llen(queue) or 0)
    except Exception as exc:  # pragma: no cover
        logger.warning("Celery növbə uzunluğu oxunmadı: %s", exc)
    return lengths


def collect_backup_age() -> float | None:
    """Beat task-ı: ən yeni backup faylının yaşını cache-ə yaz (saniyə)."""
    newest: float | None = None
    if os.path.isdir(BACKUP_DIR):
        for root, _dirs, files in os.walk(BACKUP_DIR):
            for name in files:
                if not name.endswith((".sql.gz", ".sql", ".dump")):
                    continue
                try:
                    mtime = os.path.getmtime(os.path.join(root, name))
                except OSError:
                    continue
                if newest is None or mtime > newest:
                    newest = mtime
    age = None if newest is None else max(0.0, time.time() - newest)
    cache.set(BACKUP_CACHE_KEY, {"age_seconds": age, "collected_at": time.time()}, CACHE_TTL)
    return age


class _CacheGaugeCollector:
    """Scrape zamanı cache-dən oxuyan Prometheus kollektoru (app prosesində)."""

    def collect(self):  # pragma: no cover - scrape yolu inteqrasiyada yoxlanır
        from prometheus_client.core import GaugeMetricFamily

        stats = cache.get(CACHE_KEY)
        if stats:
            yield GaugeMetricFamily(
                "emsarena_celery_workers_online",
                "Onlayn Celery worker sayı",
                value=stats.get("workers_online", 0),
            )
            yield GaugeMetricFamily(
                "emsarena_celery_active_tasks", "İcradakı task sayı", value=stats.get("active_tasks", 0)
            )
            yield GaugeMetricFamily(
                "emsarena_celery_reserved_tasks",
                "Reserved task sayı",
                value=stats.get("reserved_tasks", 0),
            )
            # P2-8: növbə etiketli gauge-lar. Köhnə cache formatında (yalnız
            # `queue_length`) heavy sırası 0 kimi verilir ki, seriya itməsin.
            lengths = stats.get("queue_lengths") or {"celery": stats.get("queue_length", 0)}
            queue_length = GaugeMetricFamily(
                "emsarena_celery_queue_length",
                "Broker növbəsinin uzunluğu (növbə üzrə)",
                labels=["queue"],
            )
            for queue in MONITORED_QUEUES:
                queue_length.add_metric([queue], lengths.get(queue, 0))
            yield queue_length
            # Köhnə formatlı cache-də (rollout pəncərəsi) bu açar yoxdur —
            # seriyanı verməmək yalançı CeleryHeavyWorkerDown-dan qoruyur.
            workers = stats.get("queue_workers")
            if workers is not None:
                queue_workers = GaugeMetricFamily(
                    "emsarena_celery_queue_workers",
                    "Növbəni dinləyən onlayn worker sayı (heavy worker ölümü üçün)",
                    labels=["queue"],
                )
                for queue in MONITORED_QUEUES:
                    queue_workers.add_metric([queue], workers.get(queue, 0))
                yield queue_workers
            yield GaugeMetricFamily(
                "emsarena_celery_stats_collected_timestamp",
                "Statistikanın toplandığı unix vaxtı (beat sağlamlıq siqnalı)",
                value=stats.get("collected_at", 0),
            )
        backup = cache.get(BACKUP_CACHE_KEY)
        if backup and backup.get("age_seconds") is not None:
            yield GaugeMetricFamily(
                "emsarena_backup_age_seconds",
                "Ən yeni PostgreSQL backup faylının yaşı",
                value=backup["age_seconds"],
            )


_registered = False


def register_cache_collector():
    """Kollektoru core REGISTRY-yə bir dəfə əlavə et (app ready())."""
    global _registered
    if _registered:  # pragma: no cover
        return
    try:
        from core.metrics import REGISTRY

        REGISTRY.register(_CacheGaugeCollector())
        _registered = True
    except Exception as exc:  # pragma: no cover - prometheus_client yoxdursa
        logger.warning("Monitorinq kollektoru qeydə alınmadı: %s", exc)
