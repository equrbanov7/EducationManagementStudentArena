"""Prometheus / Loki / Alertmanager server-tərəfli müştəriləri.

Frontend HEÇ VAXT bu servislərə birbaşa çıxmır — bütün sorğular Django
backend-indən, timeout + qısa cache + degraded-fallback ilə gedir. Monitorinq
asılılığı əlçatmaz olsa API 200 qaytarır, amma ``status="degraded"`` ilə —
UI bunu ayrıca göstərir (imtahan sisteminə heç bir təsir yoxdur).
"""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache

import requests

logger = logging.getLogger(__name__)

#: Monitorinq backend sorğuları üçün qısa timeout — istifadəçi səhifəsi
#: asılılıq problemində maksimum bu qədər gözləyir.
REQUEST_TIMEOUT_SECONDS = 5
#: Eyni sorğunun cache müddəti (auto-refresh fırtınasının qarşısı).
CACHE_TTL_SECONDS = 10
#: Loki sorğularının sərt limitləri (performans tələbi).
LOKI_MAX_LINES = 500
LOKI_MAX_RANGE_SECONDS = 7 * 24 * 3600


def _base_urls() -> dict[str, str]:
    return {
        "prometheus": getattr(settings, "MONITORING_PROMETHEUS_URL", "http://prometheus:9090"),
        "loki": getattr(settings, "MONITORING_LOKI_URL", "http://loki:3100"),
        "alertmanager": getattr(settings, "MONITORING_ALERTMANAGER_URL", "http://alertmanager:9093"),
    }


def degraded(service: str, message: str) -> dict[str, Any]:
    """Vahid degraded-cavab forması (UI bunun üzərinə boz vəziyyət çəkir)."""
    last_ok = cache.get(f"monitoring:last_ok:{service}")
    return {
        "status": "degraded",
        "service": service,
        "message": message,
        "last_successful_update": last_ok,
    }


def _get_json(service: str, path: str, params: dict | None = None) -> dict | None:
    """GET + JSON; cache-lənir; xətada None (çağıran degraded qaytarır)."""
    import hashlib

    base = _base_urls()[service]
    raw_key = f"{service}:{path}:{urlencode(sorted((params or {}).items()))}"
    # Yalnız cache-açar qısaltması üçündür (memcached 250-simvol limiti) —
    # kriptoqrafik məqsəd yoxdur.
    cache_key = "monitoring:q:" + hashlib.md5(raw_key.encode(), usedforsecurity=False).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        response = requests.get(f"{base}{path}", params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning("Monitorinq %s sorğusu alınmadı (%s): %s", service, path, exc)
        return None

    cache.set(cache_key, payload, CACHE_TTL_SECONDS)
    cache.set(f"monitoring:last_ok:{service}", time.strftime("%Y-%m-%dT%H:%M:%S%z"), None)
    return payload


class PrometheusClient:
    service = "prometheus"

    def query(self, promql: str) -> list[dict] | None:
        """Ani sorğu → result siyahısı ([] boş, None = xidmət əlçatmaz)."""
        payload = _get_json(self.service, "/api/v1/query", {"query": promql})
        if payload is None or payload.get("status") != "success":
            return None
        return payload["data"].get("result", [])

    def query_range(self, promql: str, *, start: float, end: float, step: str) -> list[dict] | None:
        payload = _get_json(
            self.service,
            "/api/v1/query_range",
            {"query": promql, "start": start, "end": end, "step": step},
        )
        if payload is None or payload.get("status") != "success":
            return None
        return payload["data"].get("result", [])

    def scalar(self, promql: str, default: float | None = None) -> float | None:
        """Tək-vektorlu sorğunun ilk dəyəri (yoxdursa default)."""
        result = self.query(promql)
        if not result:
            return default if result is not None else None
        try:
            return float(result[0]["value"][1])
        except (KeyError, IndexError, TypeError, ValueError):
            return default


class LokiClient:
    service = "loki"

    def query_range(
        self,
        logql: str,
        *,
        start_ns: int,
        end_ns: int,
        limit: int = 100,
        direction: str = "backward",
    ) -> list[dict] | None:
        limit = max(1, min(int(limit), LOKI_MAX_LINES))
        if end_ns - start_ns > LOKI_MAX_RANGE_SECONDS * 1_000_000_000:
            start_ns = end_ns - LOKI_MAX_RANGE_SECONDS * 1_000_000_000
        payload = _get_json(
            self.service,
            "/loki/api/v1/query_range",
            {
                "query": logql,
                "start": start_ns,
                "end": end_ns,
                "limit": limit,
                "direction": direction,
            },
        )
        if payload is None or payload.get("status") != "success":
            return None
        return payload["data"].get("result", [])

    def labels_values(self, label: str) -> list[str] | None:
        payload = _get_json(self.service, f"/loki/api/v1/label/{label}/values")
        if payload is None or payload.get("status") != "success":
            return None
        return payload.get("data", [])


class AlertmanagerClient:
    service = "alertmanager"

    def alerts(self) -> list[dict] | None:
        # api/v2 birbaşa siyahı qaytarır (status sahəsi yoxdur).
        payload = _get_json(self.service, "/api/v2/alerts", {"silenced": "true", "inhibited": "true"})
        return payload if isinstance(payload, list) else None

    def silences(self) -> list[dict] | None:
        payload = _get_json(self.service, "/api/v2/silences")
        return payload if isinstance(payload, list) else None
