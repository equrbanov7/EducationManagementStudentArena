"""AI təhlili üçün TƏMİZLƏNMİŞ xülasə (2026-10-01).

Xarici xidmətə (Google Gemini) yalnız bu funksiyanın qaytardığı dict gedir.
Qaydalar:

* yalnız AĞ SİYAHIDAKI sahələr — xülasədəki hər şey avtomatik keçmir;
* rəqəmlər aqreqatdır (say, faiz, yaş) — heç bir istifadəçi adı, e-poçt, IP,
  sessiya, PIN, imtahan məzmunu yoxdur;
* mətn sahələri (insident başlığı, səbəb cümləsi, endpoint yolu) əlavə olaraq
  ``scrub.scrub_personal`` / ``scrub_path``-dan keçir (müdafiə dərinliyi);
* sirr (env dəyəri, açar, DSN, traceback) xülasəyə ümumiyyətlə DÜŞMÜR.
"""

from __future__ import annotations

from .scrub import scrub_path, scrub_personal

_GB = 1024**3


def _num(value, digits: int = 1):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else round(number, digits)


def _hours(seconds):
    return None if seconds is None else round(float(seconds) / 3600, 1)


def _clean(value):
    """Rekursiv: sətirlər scrub-dan keçir, rəqəm/bool olduğu kimi qalır."""
    if isinstance(value, str):
        return scrub_personal(value)[:300]
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return value


def build_ai_snapshot(summary: dict) -> dict:
    """``summary.build_summary`` nəticəsindən AI-yə gedən qısa, təmiz dict."""
    health = summary.get("health") or {}
    traffic = summary.get("traffic") or {}
    resources = summary.get("resources") or {}
    windows = {row["key"]: row for row in traffic.get("windows", [])}

    snapshot = {
        "scope": "platform" if (summary.get("scope") or {}).get("platform") else "organization",
        "metrics_available": bool(summary.get("metrics_available")),
        "overall": {
            "level": health.get("level"),
            "problems": health.get("problems", 0),
            "warnings": health.get("warnings", 0),
            "findings": [
                {"level": item.get("level"), "what": item.get("text"), "suggested": item.get("hint")}
                for item in (health.get("reasons") or [])[:15]
            ],
        },
        "traffic": {
            f"{key}_{field}": _num((windows.get(key) or {}).get(field), 2)
            for key in ("5m", "1h", "24h")
            for field in ("requests", "errors", "error_pct")
        },
        "latency_p95_ms": traffic.get("p95_ms"),
        "requests_per_second": _num(traffic.get("rps"), 2),
        "server": {
            "uptime_days": (
                None
                if (summary.get("platform") or {}).get("server_uptime_seconds") is None
                else round(summary["platform"]["server_uptime_seconds"] / 86400, 1)
            ),
            "cpu_percent": _num(resources.get("cpu_pct")),
            "memory_percent": _num(resources.get("mem_pct")),
            "disk_percent": _num(resources.get("disk_pct")),
            "disk_free_gb": (
                None if resources.get("disk_free_bytes") is None else round(resources["disk_free_bytes"] / _GB, 1)
            ),
            "containers_alive": resources.get("containers_alive"),
            "container_restarts_24h": resources.get("restarts_24h"),
            "out_of_memory_events_24h": resources.get("oom_24h"),
            "monitoring_targets_down": len(summary.get("down_jobs") or []),
        },
        "services": [
            {
                "name": row.get("key"),
                "state": row.get("state"),
                "value": _num(row.get("value")),
                "unit": row.get("unit"),
            }
            for row in summary.get("services", [])
        ],
        "backups": [
            {"name": row.get("key"), "state": row.get("state"), "age_hours": _hours(row.get("age_seconds"))}
            for row in summary.get("backups", [])
        ],
        "exams_now": {key: _num(value) for key, value in (summary.get("exams") or {}).items()},
        "users": {key: _num(value) for key, value in (summary.get("users") or {}).items()},
        "security": {
            row["key"]: {"last_24h": row.get("h24"), "last_7d": row.get("d7")}
            for row in (summary.get("security") or {}).get("rows", [])
        },
        "incidents": {
            "open": (summary.get("incidents") or {}).get("open", 0),
            "critical_open": (summary.get("incidents") or {}).get("critical_open", 0),
            "total_last_7d": (summary.get("incidents") or {}).get("total_7d", 0),
            "groups": [
                {
                    "title": group.get("title"),
                    "severity": group.get("severity"),
                    "times": group.get("count"),
                    "still_open": group.get("open"),
                    "last_duration_minutes": (
                        None
                        if group.get("last_duration_seconds") is None
                        else int(group["last_duration_seconds"] // 60)
                    ),
                }
                for group in (summary.get("incidents") or {}).get("groups", [])[:8]
            ],
        },
        "slowest_pages": [
            {"path": scrub_path(row.get("path")), "avg_ms": _num(row.get("value"), 0)}
            for row in (summary.get("endpoints") or {}).get("slow", [])[:5]
        ],
        "most_failing_pages_24h": [
            {"path": scrub_path(row.get("path")), "server_errors": _num(row.get("value"), 0)}
            for row in (summary.get("endpoints") or {}).get("errors", [])[:5]
        ],
    }
    return _clean(snapshot)


__all__ = ["build_ai_snapshot"]
