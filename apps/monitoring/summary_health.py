"""Xülasədən ümumi vəziyyət: ``ok`` / ``warning`` / ``problem`` + səbəblər (2026-10-01).

Qaydalar alertmanager hədləri ilə uyğunlaşdırılıb (``docker/prometheus/alerts.yml``)
ki, panel və bildirişlər eyni şeyi desin. Hər səbəb:
``{"level", "key", "text" (nə baş verir), "hint" (nə etməli), "tab" (ətraflı bölmə)}``.
Səs-küy olmasın deyə faiz qaydaları kifayət qədər trafik olduqda işləyir.
"""

from __future__ import annotations

from . import wording

_LEVEL_ORDER = {"ok": 0, "warning": 1, "problem": 2}
#: 5xx faizinin mənalı sayılması üçün son 1 saatda minimum sorğu sayı.
_MIN_REQUESTS_FOR_RATE = 50


def _reason(reasons: list, level: str, key: str, tab: str, **values) -> None:
    text, hint = wording.reason_text(key, **values)
    reasons.append({"level": level, "key": key, "text": text, "hint": hint, "tab": tab})


def _fmt(value, digits: int = 1) -> str:
    return f"{value:.{digits}f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)


def _service_checks(data: dict, reasons: list) -> None:
    services = {row["key"]: row for row in data.get("services", [])}
    database = services.get("database", {})
    if database.get("state") == "problem":
        _reason(reasons, "problem", "db_down", "database")
    elif database.get("state") == "warning":
        _reason(reasons, "warning", "db_slow", "database", ms=_fmt(database.get("value") or 0, 0))
    if services.get("cache", {}).get("state") == "problem":
        _reason(reasons, "problem", "cache_down", "redis-celery")
    if not data.get("metrics_available"):
        _reason(reasons, "warning", "metrics_down", "server")
    for key, tab in (("web", "containers"), ("probes", "application")):
        row = services.get(key, {})
        if row.get("state") == "problem":
            _reason(reasons, "problem", "service_down", tab, service=row.get("label", key))
    down_jobs = data.get("down_jobs") or []
    if down_jobs:
        _reason(reasons, "warning", "targets_down", "server", count=len(down_jobs))
    workers = services.get("workers", {})
    if workers.get("state") == "problem":
        _reason(reasons, "problem", "workers_down", "redis-celery")
    queue = (workers.get("extra") or {}).get("queue")
    if queue and queue > 200:
        _reason(reasons, "warning", "queue_backlog", "redis-celery", count=int(queue))
    scheduler = services.get("scheduler", {})
    if scheduler.get("state") == "warning":
        _reason(reasons, "warning", "workers_stale", "redis-celery", minutes=int((scheduler.get("value") or 0) // 60))
    pool = services.get("pgbouncer", {})
    if pool.get("state") == "warning":
        _reason(reasons, "warning", "pool_waiting", "database", count=int(pool.get("value") or 0))
    tls = services.get("tls", {})
    if tls.get("state") in {"warning", "problem"}:
        _reason(reasons, tls["state"], "tls_expiring", "alerts", days=tls.get("value"))


def _traffic_checks(data: dict, reasons: list) -> None:
    traffic = data.get("traffic") or {}
    hour = next((row for row in traffic.get("windows", []) if row["key"] == "1h"), {})
    if (hour.get("requests") or 0) >= _MIN_REQUESTS_FOR_RATE and hour.get("error_pct") is not None:
        pct = hour["error_pct"]
        if pct >= 5:
            _reason(reasons, "problem", "errors_high", "application", pct=_fmt(pct))
        elif pct >= 1:
            _reason(reasons, "warning", "errors_high", "application", pct=_fmt(pct))
    p95 = traffic.get("p95_ms")
    if p95 is not None and p95 >= 2000:
        level = "problem" if p95 >= 5000 else "warning"
        _reason(reasons, level, "latency_high", "application", seconds=_fmt(p95 / 1000))


def _resource_checks(data: dict, reasons: list) -> None:
    resources = data.get("resources") or {}
    for key, reason, warn, crit in (
        ("cpu_pct", "cpu_high", 85, 95),
        ("mem_pct", "memory_high", 90, 95),
        ("disk_pct", "disk_high", 85, 95),
    ):
        value = resources.get(key)
        if value is None or value < warn:
            continue
        _reason(reasons, "problem" if value >= crit else "warning", reason, "server", pct=_fmt(value, 0))
    if (resources.get("restarts_24h") or 0) > 5:
        _reason(reasons, "warning", "restarts", "containers", count=resources["restarts_24h"])
    if (resources.get("oom_24h") or 0) > 0:
        _reason(reasons, "warning", "oom", "containers", count=resources["oom_24h"])


def _backup_checks(data: dict, reasons: list) -> None:
    for row in data.get("backups", []):
        if row["state"] != "problem":
            continue
        hours = int((row.get("age_seconds") or 0) // 3600)
        if row["key"] == "local":
            _reason(reasons, "problem", "backup_old", "database", hours=hours)
        elif row["key"] == "offsite":
            _reason(reasons, "warning", "offsite_old", "database", hours=hours)


def _activity_checks(data: dict, reasons: list) -> None:
    incidents = data.get("incidents") or {}
    if incidents.get("critical_open"):
        _reason(reasons, "problem", "incidents_critical", "incidents", count=incidents["critical_open"])
    elif incidents.get("open"):
        _reason(reasons, "warning", "incidents_open", "incidents", count=incidents["open"])

    security = {row["key"]: row for row in (data.get("security") or {}).get("rows", [])}
    brute = (security.get("brute_force") or {}).get("h24") or 0
    if brute:
        _reason(reasons, "warning", "brute_force", "security-events", count=brute)
    failed = (security.get("failed_logins") or {}).get("h24") or 0
    if failed >= 200:
        _reason(reasons, "warning", "failed_logins_high", "security-events", count=failed)

    autosave = (data.get("exams") or {}).get("autosave_errors_1h") or 0
    if autosave:
        _reason(reasons, "warning", "exam_autosave", "exams", count=autosave)


def evaluate_health(data: dict) -> dict:
    reasons: list[dict] = []
    for check in (_service_checks, _traffic_checks, _resource_checks, _backup_checks, _activity_checks):
        check(data, reasons)
    reasons.sort(key=lambda item: -_LEVEL_ORDER[item["level"]])
    problems = sum(1 for item in reasons if item["level"] == "problem")
    warnings = sum(1 for item in reasons if item["level"] == "warning")
    level = "problem" if problems else "warning" if warnings else "ok"
    return {
        "level": level,
        "title": wording.health_title(level),
        "summary": wording.health_summary(level, warnings, problems),
        "reasons": reasons,
        "problems": problems,
        "warnings": warnings,
    }


__all__ = ["evaluate_health"]
