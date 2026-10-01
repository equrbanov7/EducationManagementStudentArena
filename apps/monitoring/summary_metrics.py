"""Xülasə paneli üçün Prometheus göstəriciləri (platforma səviyyəli, 2026-10-01).

Server/konteyner/HTTP metrikaları bütün tenantlar üçün ORTAQDIR (bir server) —
ona görə bu blok əhatədən asılı deyil və bir dəfə (qısa müddətə) keşlənir.

Performans qaydaları:
* əvvəl ``up`` sorğusu — Prometheus əlçatmazdırsa qalan ~40 sorğu HEÇ göndərilmir
  (dev-klonda və ya metrik stek dayananda səhifə 5 s × N gözləməsin);
* skalyar sorğular kiçik thread hovuzunda PARALEL gedir (hər biri
  ``clients.REQUEST_TIMEOUT_SECONDS`` ilə məhduddur);
* nəticə ``SUMMARY_METRICS_TTL`` saniyə keşdə qalır — auto-refresh fırtınası
  Prometheus-a çatmır.

Heç bir istifadəçi/PIN/IP etiketi sorğulanmır — yalnız aqreqat saylar.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from django.core.cache import cache

from . import queries
from .clients import PrometheusClient

logger = logging.getLogger(__name__)

SUMMARY_METRICS_TTL = 20
_CACHE_KEY = "monitoring:summary:metrics:v1"
_MAX_WORKERS = 6

_5XX = 'status_code=~"5.."'
_CONTAINERS = queries.CONTAINER_RE

#: ad → PromQL (skalyar). ``None`` nəticə = metrik yoxdur (UI «—» göstərir).
SCALAR_QUERIES: dict[str, str] = {
    "requests_5m": "sum(increase(http_requests_total[5m]))",
    "requests_1h": "sum(increase(http_requests_total[1h]))",
    "requests_24h": "sum(increase(http_requests_total[24h]))",
    "errors_5m": f"sum(increase(http_requests_total{{{_5XX}}}[5m]))",
    "errors_1h": f"sum(increase(http_requests_total{{{_5XX}}}[1h]))",
    "errors_24h": f"sum(increase(http_requests_total{{{_5XX}}}[24h]))",
    "forbidden_24h": 'sum(increase(http_requests_total{status_code="403"}[24h]))',
    "forbidden_7d": 'sum(increase(http_requests_total{status_code="403"}[7d]))',
    "throttled_24h": 'sum(increase(http_requests_total{status_code="429"}[24h]))',
    "throttled_7d": 'sum(increase(http_requests_total{status_code="429"}[7d]))',
    "rps": "sum(rate(http_requests_total[5m]))",
    "p95_seconds": "histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[15m])))",
    "cpu_percent": '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))',
    "memory_percent": "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)",
    "disk_percent": queries.ROOT_DISK_USED_PERCENT_PROMQL,
    "disk_free_bytes": queries.ROOT_DISK_FREE_PROMQL,
    "disk_total_bytes": queries.ROOT_DISK_TOTAL_PROMQL,
    "server_uptime_seconds": "node_time_seconds - node_boot_time_seconds",
    "containers_alive": f"count(time() - container_last_seen{{{_CONTAINERS}}} < 60)",
    "restarts_24h": f"sum(changes(container_start_time_seconds{{{_CONTAINERS}}}[24h]))",
    "oom_24h": f"sum(increase(container_oom_events_total{{{_CONTAINERS}}}[24h]))",
    "pg_up": "pg_up",
    "pg_connections": "sum(pg_stat_activity_count)",
    "pg_max_connections": "pg_settings_max_connections",
    "pool_waiting": "sum(pgbouncer_pools_client_waiting_connections)",
    "redis_up": "redis_up",
    "nginx_up": "nginx_up",
    "probes_up": 'min(probe_success{job="emsarena-blackbox"})',
    "tls_seconds_left": "min(probe_ssl_earliest_cert_expiry) - time()",
    "backup_age_seconds": "emsarena_backup_age_seconds",
    "offsite_last_success": "emsarena_offsite_backup_last_success_timestamp_seconds",
    "offsite_configured": "emsarena_offsite_backup_configured",
    "drill_last_success": "emsarena_restore_drill_last_success_timestamp_seconds",
    "autosave_errors_1h": 'sum(increase(exam_autosave_total{outcome="error"}[1h]))',
    "pin_failures_1h": 'sum(increase(exam_pin_attempt_total{outcome!="ok"}[1h]))',
    "celery_workers": "emsarena_celery_workers_online",
    "celery_queue": "sum(emsarena_celery_queue_length)",
    "celery_collected_at": "emsarena_celery_stats_collected_timestamp",
}

_SLOW_PROMQL = (
    "topk(6, sum by (path) (rate(http_request_duration_seconds_sum[1h]))"
    " / clamp_min(sum by (path) (rate(http_request_duration_seconds_count[1h])), 0.0001))"
)
_ERROR_PROMQL = f"topk(6, sum by (path) (increase(http_requests_total{{{_5XX}}}[24h])) > 0)"
_IGNORED_PATHS = frozenset({"/metrics/", "/health/", "/ping/"})


def _rows(result, *, scale: float = 1.0) -> list[dict]:
    rows = []
    for item in result or []:
        try:
            path = item["metric"].get("path", "?")
            value = float(item["value"][1]) * scale
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        if path in _IGNORED_PATHS or value != value:  # NaN
            continue
        rows.append({"path": path[:160], "value": round(value, 1)})
    return rows[:5]


def _down_jobs(targets) -> list[str]:
    status: dict[str, bool] = {}
    for item in targets or []:
        job = item.get("metric", {}).get("job", "?")
        try:
            up = float(item["value"][1]) == 1.0
        except (KeyError, IndexError, TypeError, ValueError):
            up = False
        status[job] = status.get(job, True) and up
    return sorted(job for job, ok in status.items() if not ok)


def _scalars(prom: PrometheusClient) -> dict:
    names = list(SCALAR_QUERIES)
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="mon-summary") as pool:
        values = list(pool.map(lambda name: prom.scalar(SCALAR_QUERIES[name]), names))
    result = {}
    for name, value in zip(names, values):
        if value is not None and value == value:  # NaN-ı at
            result[name] = value
        else:
            result[name] = None
    return result


def _series(prom: PrometheusClient, promql: str) -> list[list[float]]:
    data = queries._series(prom, promql, 24 * 3600) or []
    return data[0]["points"] if data else []


def collect_metrics() -> dict:
    """Prometheus blokunu qaytarır: ``{"available": bool, ...}`` (keşli)."""
    cached = cache.get(_CACHE_KEY)
    if cached is not None:
        return cached

    prom = PrometheusClient()
    targets = prom.query("up")
    if targets is None:
        block = {"available": False}
        # Əlçatmazlıq da qısa keşlənir — hər auto-refresh yenidən timeout gözləməsin.
        cache.set(_CACHE_KEY, block, SUMMARY_METRICS_TTL)
        return block

    started = time.monotonic()
    block = {
        "available": True,
        "down_jobs": _down_jobs(targets),
        "values": _scalars(prom),
        "slow_endpoints": _rows(prom.query(_SLOW_PROMQL), scale=1000.0),
        "error_endpoints": _rows(prom.query(_ERROR_PROMQL)),
        "series": {
            "requests": _series(prom, "sum(rate(http_requests_total[15m]))"),
            "errors": _series(prom, f"sum(rate(http_requests_total{{{_5XX}}}[15m]))"),
        },
    }
    logger.debug("Monitorinq xülasə metrikaları %.0f ms", (time.monotonic() - started) * 1000)
    cache.set(_CACHE_KEY, block, SUMMARY_METRICS_TTL)
    return block


__all__ = ["SCALAR_QUERIES", "SUMMARY_METRICS_TTL", "collect_metrics"]
