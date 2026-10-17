"""«Loglar» tabı: LogQL qurucusu, vaxt pəncərəsi və Loki cavabının UI formasına salınması.

2026-10-17 (sahib: «Sistem monitorinqində loglar boş göstərir»): əvvəl Loki-yə
qoşulmaq alınmayanda da, sorğu boş qayıdanda da UI eyni «məlumat yoxdur»
mətnini göstərirdi — səbəb görünmürdü. İndi:

* xəta cavabı ``error`` (növ + HTTP status + qısa izah) və ``query`` (LogQL + aralıq) daşıyır;
* boş nəticədə ``query`` + ``streams_known`` (Loki-nin son 6 saatda tanıdığı konteyner
  axınlarının sayı) qaytarılır — 0-dırsa problem göndərəndədir (promtail), sorğuda deyil;
* nanosaniyə kursorları (``anchor_ns``/``before_ns``/``next_cursor_ns``) SƏTİR kimi
  qaytarılır: ~1.7e18 JS ``Number``-in dəqiq tam ədəd sərhədini (2^53) aşır və brauzer
  onu ~128 ns yuvarlaqlaşdırırdı (2-ci səhifədə sətir təkrarı/itkisi).

Saf funksiyalardır (şəbəkə yalnız ötürülən ``client`` ilə) — test üçün asan.
"""

from __future__ import annotations

import json
import time
from typing import Any

from .clients import LOKI_MAX_LINES, LOKI_MAX_RANGE_SECONDS, degraded
from .pagination import paginated_data
from .scrub import scrub_log_line

#: Konteyner seçilməyəndə bütün promtail axınları (``docker/promtail/promtail-config.yml``
#: ``job: docker`` etiketi qoyur).
DEFAULT_SELECTOR = '{job="docker"}'
LEVELS = frozenset({"error", "warning", "critical"})
NS_PER_SECOND = 1_000_000_000


def build_logql(container: str = "", search: str = "", level: str = "") -> str:
    """İstifadəçi filtrlərindən LogQL: konteyner dəqiq matcher-dir, mətn ``|=``, səviyyə ``|~``."""
    container = (container or "").strip()[:80]
    search = (search or "").strip()[:120]
    level = (level or "").strip().lower()
    logql = f"{{container={json.dumps(container, ensure_ascii=False)}}}" if container else DEFAULT_SELECTOR
    if search:
        # Backtick LogQL sətri «raw»dır: ``\`` hərfi qalır (ikiqatlaşdırma «\» axtarışını pozurdu, SEC-1 F4).
        escaped = search.replace("`", "")
        logql += f" |= `{escaped}`"
    if level in LEVELS:
        logql += f" |~ `(?i){level}`"
    return logql


def effective_range_seconds(range_seconds: int) -> int:
    """UI aralığı (artıq ``queries.clamp_range``-dən keçib) Loki-nin sərt tavanına salınır."""
    return max(1, min(int(range_seconds), LOKI_MAX_RANGE_SECONDS))


def _int_param(params, name: str, default: int) -> int:
    try:
        return int(params.get(name, default))
    except (TypeError, ValueError):
        return default


def time_window(params, *, range_seconds: int, page: int, now_ns: int | None = None) -> dict[str, int]:
    """``[start_ns, end_ns]`` pəncərəsi: 1-ci səhifə həmişə «indi»dən, sonrakılar kursordan."""
    now_ns = time.time_ns() if now_ns is None else now_ns
    anchor_ns = max(1, min(_int_param(params, "anchor_ns", now_ns), now_ns))
    before_raw = params.get("before_ns")
    if page > 1 and not before_raw:
        page = 1
    end_ns = _int_param(params, "before_ns", anchor_ns) if before_raw else anchor_ns
    end_ns = max(1, min(end_ns, anchor_ns))
    start_ns = max(0, anchor_ns - range_seconds * NS_PER_SECOND)
    end_ns = max(start_ns, end_ns)
    return {"page": page, "anchor_ns": anchor_ns, "start_ns": start_ns, "end_ns": end_ns}


def shape_lines(result: list[dict]) -> list[dict[str, Any]]:
    """Loki ``streams`` nəticəsini ən yenisi birinci sətirlərə çevirir (sirlər və şəxsi məlumat maskalanır)."""
    lines = []
    for stream in result or []:
        labels = stream.get("stream", {}) or {}
        for value in stream.get("values", []) or []:
            try:
                ts_ns = int(value[0])
                line = str(value[1])
            except (TypeError, ValueError, IndexError):
                continue
            lines.append(
                {
                    "_ts_ns": ts_ns,
                    "ts": ts_ns // 1_000_000,  # ms
                    "container": labels.get("container", ""),
                    # SEC-1 F4: sirlər + şəxsi məlumat (İP, e-poçt, istifadəçi adı, bərpa tokeni) — hamıya.
                    "line": scrub_log_line(line[:1000]),
                }
            )
    lines.sort(key=lambda row: (row["_ts_ns"], row["container"], row["line"]), reverse=True)
    return lines


def query_info(logql: str, range_seconds: int) -> dict[str, Any]:
    return {"logql": logql, "range_seconds": range_seconds}


def error_response(error: dict | None, logql: str, range_seconds: int) -> dict[str, Any]:
    """Loki xətası: köhnə degraded müqaviləsi + UI üçün səbəb və sorğu."""
    payload = degraded("loki", "Log servisi müvəqqəti əlçatmazdır")
    payload["error"] = dict(error) if isinstance(error, dict) else {"kind": "error", "status": None, "detail": ""}
    # QA-2 F-14: Loki ``status:error`` mətni də maskalanır (sorğu mətni / sirr detalda qayıda bilər).
    payload["error"]["detail"] = scrub_log_line(payload["error"].get("detail") or "")
    payload["query"] = query_info(logql, range_seconds)
    return payload


def build_response(params, *, client, range_seconds: int, page: int, page_size: int) -> dict[str, Any]:
    """``logs/`` API cavabı (``views.logs_api``): ``status`` ok və ya degraded."""
    range_seconds = effective_range_seconds(range_seconds)
    logql = build_logql(params.get("container"), params.get("q"), params.get("level"))
    max_log_page = max(1, (LOKI_MAX_LINES + page_size - 1) // page_size)
    window = time_window(params, range_seconds=range_seconds, page=min(page, max_log_page))
    page = window["page"]

    result = client.query_range(
        logql,
        start_ns=window["start_ns"],
        end_ns=window["end_ns"],
        limit=min(page_size + 1, LOKI_MAX_LINES),
    )
    if result is None:
        return error_response(getattr(client, "last_error", None), logql, range_seconds)

    lines = shape_lines(result)
    page_lines = lines[:page_size]
    has_next = len(lines) > page_size
    next_cursor_ns = max(1, page_lines[-1]["_ts_ns"] - 1) if has_next and page_lines else None
    for row in page_lines:
        row.pop("_ts_ns", None)
    containers = client.labels_values("container")
    data = paginated_data(
        "lines",
        page_lines,
        total=(page - 1) * page_size + len(page_lines) + int(has_next),
        page=page,
        page_size=page_size,
        has_next=has_next,
        total_pages=page + int(has_next),
        total_exact=not has_next,
        extra={
            "containers": containers or [],
            # None = label sorğusu da alınmadı (bilinmir); 0 = Loki-də heç bir axın yoxdur.
            "streams_known": None if containers is None else len(containers),
            "anchor_ns": str(window["anchor_ns"]),
            "before_ns": str(window["end_ns"]),
            "next_cursor_ns": str(next_cursor_ns) if next_cursor_ns is not None else None,
            "query": query_info(logql, range_seconds),
        },
    )
    return {"status": "ok", "data": data}


__all__ = [
    "DEFAULT_SELECTOR",
    "build_logql",
    "build_response",
    "effective_range_seconds",
    "error_response",
    "shape_lines",
    "time_window",
]
