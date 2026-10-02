"""«Ümumi vəziyyət» xülasəsi — texniki olmayan oxucu üçün bir baxışda server (2026-10-01).

Sahib: «RİM rəhbəri hər şeyi görsün ki, serverdə nə baş verdiyini anlasın».
Bu modul üç mənbəni birləşdirir və nəticəni İNSAN DİLİNDƏ verir:

* ``summary_metrics`` — Prometheus (server, HTTP, konteyner, backup metrikaları);
* ``summary_db`` — baza (təhlükəsizlik hadisələri, imtahan fəaliyyəti, aktiv
  istifadəçilər, insidentlər) — əhatəli (platforma / öz təşkilatı);
* yerli yoxlamalar — baza ``SELECT 1``, keş ping-i, Celery/backup kollektorlarının
  keşdəki son statistikası (Prometheus dayansa belə işləyir).

Sonra ``evaluate_health`` ümumi vəziyyəti (``ok`` / ``warning`` / ``problem``)
və SƏBƏBLƏRİ («nə baş verir» + «nə etməli») çıxarır. Nəticə əhatə + dil üzrə
``SUMMARY_TTL`` saniyə keşlənir. Şəxsi məlumat (ad, e-poçt, IP) YOXDUR.
"""

from __future__ import annotations

import os
import time

from django.core.cache import cache
from django.utils import timezone
from django.utils.translation import get_language

from . import collectors, summary_db, wording
from .summary_health import evaluate_health
from .summary_metrics import collect_metrics

SUMMARY_TTL = 20
_CACHE_PREFIX = "monitoring:summary:v1"

#: Celery statistikasının «köhnə» sayıldığı yaş (beat hər 1–5 dəqiqədə yazır).
CELERY_STALE_SECONDS = 15 * 60
BACKUP_MAX_AGE_SECONDS = 26 * 3600


def _cache_ping() -> dict:
    from django.core.cache import caches
    from django.core.cache.backends.dummy import DummyCache

    backend = caches["default"]
    name = backend.__class__.__name__.replace("Cache", "")[:30] or "cache"
    if isinstance(backend, DummyCache):
        # Keş qəsdən söndürülüb (test/dev) — «dayanıb» deyil, «məlumat yoxdur».
        return {"ok": None, "ms": None, "backend": name}
    started = time.monotonic()
    token = str(time.time())
    try:
        backend.set("monitoring:summary:ping", token, 30)
        ok = backend.get("monitoring:summary:ping") == token
    except Exception:  # pragma: no cover - keş düşübsə xülasə yenə qaytarılır
        ok = False
    return {"ok": ok, "ms": round((time.monotonic() - started) * 1000, 1), "backend": name}


def _celery_from_cache() -> dict:
    stats = cache.get(collectors.CACHE_KEY) or {}
    if not stats:
        return {"known": False}
    collected = stats.get("collected_at") or 0
    lengths = stats.get("queue_lengths") or {"celery": stats.get("queue_length", 0)}
    return {
        "known": True,
        "workers": int(stats.get("workers_online") or 0),
        "active": int(stats.get("active_tasks") or 0),
        "queue": int(sum(int(value or 0) for value in lengths.values())),
        "age_seconds": max(0, int(time.time() - collected)) if collected else None,
    }


def _backup_from_cache() -> float | None:
    return collectors.backup_age_from_cache()


def _platform_info(metrics: dict) -> dict:
    from core.health_build_info import get_build_info

    build = get_build_info()
    sha = (build.get("sha") or "unknown")[:12]
    values = metrics.get("values") or {}
    # docker-compose.prod.yml `APP_VERSION: ${APP_VERSION:-unknown}` — hərfi «unknown» versiya deyil (2026-10-02).
    env_version = (os.getenv("APP_VERSION") or "").strip()[:40]
    if env_version.lower() == "unknown":
        env_version = ""
    return {
        "version": env_version or sha,
        "sha": sha,
        "built_at": build.get("built_at"),
        "server_uptime_seconds": values.get("server_uptime_seconds"),
    }


def _state(ok, *, warn: bool = False) -> str:
    if ok is None:
        return "unknown"
    if not ok:
        return "problem"
    return "warning" if warn else "ok"


def _services(metrics: dict, local: dict) -> list[dict]:
    values = metrics.get("values") or {}
    available = metrics.get("available", False)
    db = local["database"]
    cache_info = local["cache"]
    celery = local["celery"]

    def _up(name):
        value = values.get(name)
        return None if value is None else value == 1.0

    connections = values.get("pg_connections")
    max_connections = values.get("pg_max_connections")
    waiting = values.get("pool_waiting")
    workers = celery["workers"] if celery.get("known") else values.get("celery_workers")
    queue = celery["queue"] if celery.get("known") else values.get("celery_queue")
    age = celery.get("age_seconds") if celery.get("known") else None
    if age is None and values.get("celery_collected_at"):
        age = max(0, int(time.time() - values["celery_collected_at"]))
    tls_days = None if values.get("tls_seconds_left") is None else int(values["tls_seconds_left"] // 86400)

    rows = [
        {
            "key": "database",
            "state": _state(db["ok"], warn=bool(db["ms"] and db["ms"] > 200)),
            "value": db["ms"],
            "unit": "ms",
            "extra": {"connections": connections, "max_connections": max_connections},
        },
        {
            "key": "pgbouncer",
            "state": "unknown" if waiting is None else ("warning" if waiting > 0 else "ok"),
            "value": waiting,
            "unit": "waiting",
        },
        {
            "key": "cache",
            "state": _state(cache_info["ok"] and _up("redis_up") is not False),
            "value": cache_info["ms"],
            "unit": "ms",
        },
        {
            "key": "workers",
            "state": "unknown" if workers is None else ("problem" if workers < 1 else "ok"),
            "value": workers,
            "unit": "workers",
            "extra": {"queue": queue},
        },
        {
            "key": "scheduler",
            "state": "unknown" if age is None else ("warning" if age > CELERY_STALE_SECONDS else "ok"),
            "value": age,
            "unit": "age",
        },
        {"key": "web", "state": _state(_up("nginx_up")), "value": None, "unit": ""},
        {"key": "probes", "state": _state(_up("probes_up")), "value": None, "unit": ""},
        {
            "key": "metrics",
            "state": "ok" if available else "problem",
            "value": len(metrics.get("down_jobs") or []) if available else None,
            "unit": "down_jobs",
        },
        {
            "key": "tls",
            "state": (
                "unknown" if tls_days is None else ("problem" if tls_days < 7 else "warning" if tls_days < 30 else "ok")
            ),
            "value": tls_days,
            "unit": "days",
        },
    ]
    for row in rows:
        row["label"] = wording.service_label(row["key"])
    return rows


def _backups(metrics: dict, local_backup_age) -> list[dict]:
    values = metrics.get("values") or {}
    now = time.time()
    local_age = local_backup_age if local_backup_age is not None else values.get("backup_age_seconds")
    offsite_ts = values.get("offsite_last_success")
    offsite_age = (now - offsite_ts) if offsite_ts else None
    configured = values.get("offsite_configured")
    drill_ts = values.get("drill_last_success")
    drill_age = (now - drill_ts) if drill_ts else None

    def _age_state(age, limit):
        if age is None:
            return "unknown"
        return "problem" if age > limit else "ok"

    rows = [
        {"key": "local", "age_seconds": local_age, "state": _age_state(local_age, BACKUP_MAX_AGE_SECONDS)},
        {
            "key": "offsite",
            "age_seconds": offsite_age,
            "state": "unknown" if configured != 1.0 else _age_state(offsite_age, BACKUP_MAX_AGE_SECONDS),
        },
        {"key": "drill", "age_seconds": drill_age, "state": _age_state(drill_age, 35 * 86400)},
    ]
    for row in rows:
        row["label"] = wording.backup_label(row["key"])
        if row["state"] == "problem" and row["key"] == "drill":
            row["state"] = "warning"
    return rows


def _traffic(metrics: dict) -> dict:
    values = metrics.get("values") or {}
    windows = []
    for key in ("5m", "1h", "24h"):
        requests = values.get(f"requests_{key}")
        errors = values.get(f"errors_{key}")
        pct = None
        if requests:
            pct = round(100.0 * (errors or 0) / requests, 2)
        windows.append(
            {
                "key": key,
                "label": wording.window_label(key),
                "requests": None if requests is None else int(round(requests)),
                "errors": None if errors is None else int(round(errors)),
                "error_pct": pct,
            }
        )
    p95 = values.get("p95_seconds")
    return {
        "windows": windows,
        "rps": None if values.get("rps") is None else round(values["rps"], 2),
        "p95_ms": None if p95 is None else int(p95 * 1000),
        "series": metrics.get("series") or {"requests": [], "errors": []},
    }


def _security_rows(counts: dict, metrics: dict) -> list[dict]:
    values = metrics.get("values") or {}
    keys = (
        "failed_logins",
        "brute_force",
        "network_zone",
        "profanity",
        "permission_denials",
        "admin_denials",
        "superadmin_failed",
        "unauthorized_monitoring",
    )
    rows = [{"key": key, "h24": counts.get(f"{key}_24h", 0), "d7": counts.get(f"{key}_7d", 0)} for key in keys]
    for key, prom_key in (("http_forbidden", "forbidden"), ("rate_limited", "throttled")):
        h24, d7 = values.get(f"{prom_key}_24h"), values.get(f"{prom_key}_7d")
        rows.append(
            {
                "key": key,
                "h24": None if h24 is None else int(round(h24)),
                "d7": None if d7 is None else int(round(d7)),
            }
        )
    alert_keys = {"brute_force", "superadmin_failed", "unauthorized_monitoring"}
    for row in rows:
        row["label"] = wording.security_label(row["key"])
        row["state"] = "warning" if row["key"] in alert_keys and (row["h24"] or 0) > 0 else "ok"
    return rows


def _resources(metrics: dict) -> dict:
    values = metrics.get("values") or {}

    def _round(name, digits=1):
        value = values.get(name)
        return None if value is None else round(value, digits)

    return {
        "cpu_pct": _round("cpu_percent"),
        "mem_pct": _round("memory_percent"),
        "disk_pct": _round("disk_percent"),
        "disk_free_bytes": values.get("disk_free_bytes"),
        "disk_total_bytes": values.get("disk_total_bytes"),
        "containers_alive": None if values.get("containers_alive") is None else int(values["containers_alive"]),
        "restarts_24h": None if values.get("restarts_24h") is None else int(values["restarts_24h"]),
        "oom_24h": None if values.get("oom_24h") is None else int(round(values["oom_24h"])),
    }


def build_summary(scope, *, use_cache: bool = True) -> dict:
    """Xülasə payload-u (``data`` hissəsi). Əhatə + dil üzrə keşlənir."""
    cache_key = f"{_CACHE_PREFIX}:{scope.cache_key}:{get_language() or 'az'}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    now = timezone.now()
    metrics = collect_metrics()
    local = {
        "database": summary_db.database_ping(),
        "cache": _cache_ping(),
        "celery": _celery_from_cache(),
    }
    values = metrics.get("values") or {}
    exams = summary_db.exam_activity(scope, now)
    exams["autosave_errors_1h"] = (
        None if values.get("autosave_errors_1h") is None else int(values["autosave_errors_1h"])
    )
    exams["pin_failures_1h"] = None if values.get("pin_failures_1h") is None else int(values["pin_failures_1h"])

    data = {
        "generated_at": now.isoformat(),
        "scope": {"platform": scope.platform},
        "metrics_available": bool(metrics.get("available")),
        "platform": _platform_info(metrics),
        "traffic": _traffic(metrics),
        "endpoints": {
            "slow": metrics.get("slow_endpoints") or [],
            "errors": metrics.get("error_endpoints") or [],
        },
        "services": _services(metrics, local),
        "resources": _resources(metrics),
        "backups": _backups(metrics, _backup_from_cache()),
        "exams": exams,
        "users": summary_db.user_activity(scope, now),
        "security": {"rows": _security_rows(summary_db.security_counts(scope, now), metrics)},
        "incidents": summary_db.incidents_digest(now),
        "down_jobs": metrics.get("down_jobs") or [],
    }
    data["health"] = evaluate_health(data)
    cache.set(cache_key, data, SUMMARY_TTL)
    return data


__all__ = ["SUMMARY_TTL", "build_summary"]
