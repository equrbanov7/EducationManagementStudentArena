"""Bölmə-bölmə PromQL sorğuları və nəticələrin API-yə uyğun formaya salınması.

Bütün funksiyalar ya ``{"status": "ok", "data": ...}`` ya da clients.degraded()
qaytarır. Etiketlər aşağı-kardinallıqlıdır; heç bir istifadəçi/PIN/imtahan
məzmunu sorğulara düşmür.
"""

from __future__ import annotations

import time
from typing import Any

from .clients import PrometheusClient, degraded

#: cAdvisor-da izlədiyimiz konteyner adları nümunəsi.
CONTAINER_RE = 'name=~"emsarena-.+|educationmanagementstudentarena-.+"'

#: UI vaxt-aralığı seçicisinin təhlükəsiz addımları.
RANGE_STEPS = {
    300: "15s",
    900: "30s",
    3600: "60s",
    6 * 3600: "5m",
    24 * 3600: "15m",
    7 * 24 * 3600: "2h",
    30 * 24 * 3600: "8h",
}
MAX_RANGE_SECONDS = 30 * 24 * 3600


def clamp_range(seconds: int) -> tuple[int, str]:
    """İstifadəçi seçimini dəstəklənən aralığa/addıma sal."""
    seconds = max(300, min(int(seconds or 3600), MAX_RANGE_SECONDS))
    best = min(RANGE_STEPS, key=lambda known: abs(known - seconds))
    return best, RANGE_STEPS[best]


def _series(prom: PrometheusClient, promql: str, range_seconds: int) -> list[dict] | None:
    range_seconds, step = clamp_range(range_seconds)
    end = time.time()
    result = prom.query_range(promql, start=end - range_seconds, end=end, step=step)
    if result is None:
        return None
    return [
        {
            "labels": {k: v for k, v in item.get("metric", {}).items() if k != "__name__"},
            "points": [[float(ts), float(val)] for ts, val in item.get("values", [])],
        }
        for item in result
    ]


def _ok(data: Any) -> dict:
    return {"status": "ok", "data": data}


def server_section(range_seconds: int) -> dict:
    prom = PrometheusClient()
    charts = {
        "cpu": _series(prom, '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))', range_seconds),
        "memory": _series(
            prom, "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)", range_seconds
        ),
        "swap": _series(
            prom,
            "100 * (1 - node_memory_SwapFree_bytes / clamp_min(node_memory_SwapTotal_bytes, 1))",
            range_seconds,
        ),
        "load": _series(prom, "node_load1", range_seconds),
        "disk_used_percent": _series(
            prom,
            '100 * (1 - node_filesystem_avail_bytes{mountpoint="/host",fstype!~"tmpfs|overlay"}'
            ' / node_filesystem_size_bytes{mountpoint="/host",fstype!~"tmpfs|overlay"})',
            range_seconds,
        ),
        "disk_io": _series(prom, "sum(rate(node_disk_io_time_seconds_total[5m])) * 100", range_seconds),
        "net_rx": _series(
            prom, 'sum(rate(node_network_receive_bytes_total{device!~"lo|veth.*|br.*"}[5m]))', range_seconds
        ),
        "net_tx": _series(
            prom, 'sum(rate(node_network_transmit_bytes_total{device!~"lo|veth.*|br.*"}[5m]))', range_seconds
        ),
    }
    if charts["cpu"] is None:
        return degraded("prometheus", "Metrik servisi müvəqqəti əlçatmazdır")

    summary = {
        "uptime_seconds": prom.scalar("node_time_seconds - node_boot_time_seconds"),
        "cores": prom.scalar("count(count(node_cpu_seconds_total) by (cpu))"),
        "load1": prom.scalar("node_load1"),
        "load5": prom.scalar("node_load5"),
        "load15": prom.scalar("node_load15"),
        "mem_total": prom.scalar("node_memory_MemTotal_bytes"),
        "mem_available": prom.scalar("node_memory_MemAvailable_bytes"),
        "disk_total": prom.scalar('node_filesystem_size_bytes{mountpoint="/host",fstype!~"tmpfs|overlay"}'),
        "disk_free": prom.scalar('node_filesystem_avail_bytes{mountpoint="/host",fstype!~"tmpfs|overlay"}'),
        "inode_free_percent": prom.scalar(
            '100 * node_filesystem_files_free{mountpoint="/host",fstype!~"tmpfs|overlay"}'
            ' / node_filesystem_files{mountpoint="/host",fstype!~"tmpfs|overlay"}'
        ),
        "processes": prom.scalar("node_procs_running"),
        "file_descriptors": prom.scalar("node_filefd_allocated"),
    }
    return _ok({"charts": charts, "summary": summary})


def containers_section() -> dict:
    prom = PrometheusClient()
    last_seen = prom.query(f"container_last_seen{{{CONTAINER_RE}}}")
    if last_seen is None:
        return degraded("prometheus", "cAdvisor metrikaları əlçatmazdır")

    def _metric_map(promql: str) -> dict[str, float]:
        result = prom.query(promql) or []
        mapping: dict[str, float] = {}
        for item in result:
            name = item.get("metric", {}).get("name", "")
            try:
                mapping[name] = float(item["value"][1])
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        return mapping

    cpu = _metric_map(f"100 * sum by (name) (rate(container_cpu_usage_seconds_total{{{CONTAINER_RE}}}[5m]))")
    memory = _metric_map(f"sum by (name) (container_memory_usage_bytes{{{CONTAINER_RE}}})")
    mem_limit = _metric_map(f"sum by (name) (container_spec_memory_limit_bytes{{{CONTAINER_RE}}})")
    started = _metric_map(f"max by (name) (container_start_time_seconds{{{CONTAINER_RE}}})")
    restarts = _metric_map(f"changes(container_start_time_seconds{{{CONTAINER_RE}}}[24h])")
    net_rx = _metric_map(f"sum by (name) (rate(container_network_receive_bytes_total{{{CONTAINER_RE}}}[5m]))")
    net_tx = _metric_map(f"sum by (name) (rate(container_network_transmit_bytes_total{{{CONTAINER_RE}}}[5m]))")
    oom = _metric_map(f"sum by (name) (container_oom_events_total{{{CONTAINER_RE}}})")
    images: dict[str, str] = {}
    for item in last_seen:
        metric = item.get("metric", {})
        if metric.get("name"):
            images[metric["name"]] = metric.get("image", "")

    now = time.time()
    rows = []
    for item in last_seen:
        name = item.get("metric", {}).get("name", "")
        if not name:
            continue
        try:
            seen = float(item["value"][1])
        except (KeyError, IndexError, TypeError, ValueError):
            seen = 0.0
        rows.append(
            {
                "name": name,
                "alive": (now - seen) < 60,
                "uptime_seconds": max(0, int(now - started.get(name, now))),
                "cpu_percent": round(cpu.get(name, 0.0), 2),
                "memory_bytes": memory.get(name),
                "memory_limit_bytes": mem_limit.get(name) or None,
                "restarts_24h": int(restarts.get(name, 0)),
                "net_rx_bps": net_rx.get(name),
                "net_tx_bps": net_tx.get(name),
                "oom_events": int(oom.get(name, 0)),
                "image": images.get(name, ""),
            }
        )
    rows.sort(key=lambda row: row["name"])
    return _ok({"containers": rows})


def application_section(range_seconds: int) -> dict:
    prom = PrometheusClient()
    charts = {
        "request_rate": _series(prom, "sum(rate(http_requests_total[5m]))", range_seconds),
        "error_rate": _series(
            prom,
            'sum(rate(http_requests_total{status_code=~"5.."}[5m]))'
            " / clamp_min(sum(rate(http_requests_total[5m])), 0.001) * 100",
            range_seconds,
        ),
        "latency_p95": _series(
            prom,
            "histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))",
            range_seconds,
        ),
        "latency_p99": _series(
            prom,
            "histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))",
            range_seconds,
        ),
    }
    if charts["request_rate"] is None:
        return degraded("prometheus", "Metrik servisi müvəqqəti əlçatmazdır")

    def _status_class(pattern: str) -> float | None:
        return prom.scalar(f'sum(rate(http_requests_total{{status_code=~"{pattern}"}}[15m])) * 900', 0.0)

    slow = prom.query(
        "topk(8, sum by (path) (rate(http_request_duration_seconds_sum[30m]))"
        " / clamp_min(sum by (path) (rate(http_request_duration_seconds_count[30m])), 0.001))"
    )
    errors = prom.query('topk(8, sum by (path) (rate(http_requests_total{status_code=~"5.."}[30m])) * 1800)')

    def _rows(result):
        rows = []
        for item in result or []:
            try:
                rows.append({"path": item["metric"].get("path", "?"), "value": float(item["value"][1])})
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        return rows

    summary = {
        "p50": prom.scalar("histogram_quantile(0.50, sum by (le) (rate(http_request_duration_seconds_bucket[15m])))"),
        "p95": prom.scalar("histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[15m])))"),
        "p99": prom.scalar("histogram_quantile(0.99, sum by (le) (rate(http_request_duration_seconds_bucket[15m])))"),
        "status_2xx_15m": _status_class("2.."),
        "status_3xx_15m": _status_class("3.."),
        "status_4xx_15m": _status_class("4.."),
        "status_5xx_15m": _status_class("5.."),
        "status_429_15m": _status_class("429"),
        "slow_endpoints": _rows(slow),
        "error_endpoints": _rows(errors),
    }
    return _ok({"charts": charts, "summary": summary})


def database_section(range_seconds: int) -> dict:
    prom = PrometheusClient()
    up = prom.scalar("pg_up")
    if up is None:
        return degraded("prometheus", "Metrik servisi müvəqqəti əlçatmazdır")

    charts = {
        "connections": _series(prom, "sum(pg_stat_activity_count)", range_seconds),
        "tps": _series(
            prom,
            "sum(rate(pg_stat_database_xact_commit[5m]) + rate(pg_stat_database_xact_rollback[5m]))",
            range_seconds,
        ),
    }
    summary = {
        "pg_up": up,
        "active_connections": prom.scalar('sum(pg_stat_activity_count{state="active"})'),
        "idle_connections": prom.scalar('sum(pg_stat_activity_count{state="idle"})'),
        "total_connections": prom.scalar("sum(pg_stat_activity_count)"),
        "max_connections": prom.scalar("pg_settings_max_connections"),
        "commits_5m": prom.scalar("sum(rate(pg_stat_database_xact_commit[5m])) * 300"),
        "rollbacks_5m": prom.scalar("sum(rate(pg_stat_database_xact_rollback[5m])) * 300"),
        "deadlocks_1h": prom.scalar("sum(increase(pg_stat_database_deadlocks[1h]))", 0.0),
        "cache_hit_ratio": prom.scalar(
            "sum(pg_stat_database_blks_hit)"
            " / clamp_min(sum(pg_stat_database_blks_hit) + sum(pg_stat_database_blks_read), 1) * 100"
        ),
        "db_size_bytes": prom.scalar('sum(pg_database_size_bytes{datname!~"template.*|postgres"})'),
        "temp_files_1h": prom.scalar("sum(increase(pg_stat_database_temp_files[1h]))", 0.0),
        # PgBouncer (session mode — RLS GUC-ları üçün DƏYİŞDİRİLMİR).
        "pgbouncer_active_clients": prom.scalar("sum(pgbouncer_pools_client_active_connections)"),
        "pgbouncer_waiting_clients": prom.scalar("sum(pgbouncer_pools_client_waiting_connections)"),
        "pgbouncer_active_servers": prom.scalar("sum(pgbouncer_pools_server_active_connections)"),
        "pgbouncer_idle_servers": prom.scalar("sum(pgbouncer_pools_server_idle_connections)"),
        "pgbouncer_max_wait_seconds": prom.scalar("max(pgbouncer_pools_client_maxwait_seconds)"),
        "backup_age_seconds": prom.scalar("emsarena_backup_age_seconds"),
    }
    return _ok({"charts": charts, "summary": summary})


def redis_celery_section(range_seconds: int) -> dict:
    prom = PrometheusClient()
    up = prom.scalar("redis_up")
    if up is None:
        return degraded("prometheus", "Metrik servisi müvəqqəti əlçatmazdır")

    charts = {
        "redis_memory": _series(prom, "redis_memory_used_bytes", range_seconds),
        "redis_ops": _series(prom, "rate(redis_commands_processed_total[5m])", range_seconds),
        "celery_queue": _series(prom, "emsarena_celery_queue_length", range_seconds),
    }
    summary = {
        "redis_up": up,
        "redis_memory_used": prom.scalar("redis_memory_used_bytes"),
        "redis_memory_max": prom.scalar("redis_memory_max_bytes"),
        "redis_clients": prom.scalar("redis_connected_clients"),
        "redis_blocked": prom.scalar("redis_blocked_clients"),
        "redis_hit_ratio": prom.scalar(
            "rate(redis_keyspace_hits_total[15m])"
            " / clamp_min(rate(redis_keyspace_hits_total[15m]) + rate(redis_keyspace_misses_total[15m]), 0.001)"
            " * 100"
        ),
        "redis_evicted_total": prom.scalar("redis_evicted_keys_total", 0.0),
        "redis_expired_total": prom.scalar("redis_expired_keys_total", 0.0),
        "celery_workers_online": prom.scalar("emsarena_celery_workers_online"),
        "celery_active_tasks": prom.scalar("emsarena_celery_active_tasks"),
        "celery_reserved_tasks": prom.scalar("emsarena_celery_reserved_tasks"),
        "celery_queue_length": prom.scalar("emsarena_celery_queue_length"),
        "celery_stats_age_seconds": None,
    }
    collected = prom.scalar("emsarena_celery_stats_collected_timestamp")
    if collected:
        summary["celery_stats_age_seconds"] = max(0, int(time.time() - collected))
    return _ok({"charts": charts, "summary": summary})


def exams_section(range_seconds: int) -> dict:
    """Yalnız aqreqat imtahan metrikaları — heç bir sual/cavab/PIN məzmunu."""
    prom = PrometheusClient()
    charts = {
        "attempt_starts": _series(prom, "sum(rate(exam_attempt_started_total[15m])) * 900", range_seconds),
        "submissions": _series(prom, "sum(rate(exam_attempt_submitted_total[15m])) * 900", range_seconds),
        "autosave_failures": _series(prom, 'sum(rate(exam_autosave_total{outcome="error"}[15m])) * 900', range_seconds),
        "pin_failures": _series(prom, 'sum(rate(exam_pin_attempt_total{outcome!="ok"}[15m])) * 900', range_seconds),
    }
    prometheus_ok = charts["attempt_starts"] is not None

    from django.utils import timezone

    from apps.exams.models import Exam, ExamAttempt

    now = timezone.now()
    db_stats = {
        "active_exams": Exam.objects.filter(is_deleted=False, start_datetime__lte=now, end_datetime__gte=now).count(),
        "in_progress_attempts": ExamAttempt.objects.filter(status="in_progress").count(),
        "submitted_today": ExamAttempt.objects.filter(finished_at__date=now.date()).count(),
    }
    counters = {}
    if prometheus_ok:
        counters = {
            "pin_attempts_1h": prom.scalar("sum(increase(exam_pin_attempt_total[1h]))", 0.0),
            "pin_failures_1h": prom.scalar('sum(increase(exam_pin_attempt_total{outcome!="ok"}[1h]))', 0.0),
            "autosave_errors_1h": prom.scalar('sum(increase(exam_autosave_total{outcome="error"}[1h]))', 0.0),
            "supervision_incidents_1h": prom.scalar("sum(increase(exam_supervision_incident_total[1h]))", 0.0),
        }
    return _ok(
        {
            "charts": charts if prometheus_ok else None,
            "db": db_stats,
            "counters": counters,
            "metrics_degraded": not prometheus_ok,
        }
    )
