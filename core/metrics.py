"""
Application metrics definitions.

Exposes Prometheus-compatible metrics for the EMS Arena application:

- ``http_requests_total``          – Counter of HTTP requests by method, path, and
                                     HTTP status code.
- ``http_request_duration_seconds`` – Latency histogram by method and normalised path.
- ``django_app_info``               – Static Info gauge with application metadata.

The metrics are populated by ``core.middleware.MetricsMiddleware``.  The
``/metrics/`` HTTP endpoint (``core.views.metrics_view``) exposes them in the
Prometheus text exposition format.

Multi-process notes
-------------------
When Django runs under a multi-worker server (Gunicorn, Daphne) the
``prometheus_multiproc_dir`` environment variable **must** point to a shared,
writable directory.  When the variable is absent (single-process dev server or
tests) the default in-process registry is used transparently.
"""

from __future__ import annotations

import os

from prometheus_client import CollectorRegistry, Counter, Histogram, Info

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# Honour the prometheus multi-process directory when set.
_MULTIPROC_DIR = os.environ.get("prometheus_multiproc_dir") or os.environ.get("PROMETHEUS_MULTIPROC_DIR")

if _MULTIPROC_DIR:
    # Multi-process mode: each worker writes to individual .db files in the
    # shared directory; a custom registry is needed so we can aggregate them.
    from prometheus_client import multiprocess

    REGISTRY: CollectorRegistry = CollectorRegistry()
    multiprocess.MultiProcessCollector(REGISTRY)
else:
    # Single-process (default dev / test) – reuse the global default registry.
    from prometheus_client import REGISTRY  # type: ignore[assignment]  # noqa: F811

# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

#: Total number of HTTP requests handled, labelled by HTTP method, normalised
#: URL path, and response status code.
http_requests_total = Counter(
    "http_requests_total",
    "Total count of HTTP requests handled by the Django application",
    ["method", "path", "status_code"],
)

#: Request latency histogram, labelled by HTTP method and normalised URL path.
#: Buckets cover the range from 5 ms to 10 s to accommodate both fast API
#: responses and slower page renders / file uploads.
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

#: Static application metadata gauge (version, environment).
django_app_info = Info(
    "django_app",
    "EMS Arena application metadata",
)
django_app_info.info(
    {
        "version": os.getenv("APP_VERSION", "unknown"),
        "environment": os.getenv("APP_ENV", "unknown"),
    }
)


def _normalise_path(path: str) -> str:
    """Collapse dynamic path segments to reduce cardinality of metric labels.

    Examples::

        /courses/42/detail/   → /courses/<id>/detail/
        /api/v1/live/ABCD1234EF/state/ → /api/v1/live/<pin>/state/
        /media/download/some/file.pdf  → /media/download/<path>

    Paths that contain only static segments are returned unchanged.
    """
    import re

    # UUIDs
    path = re.sub(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "/<uuid>", path)
    # Live-exam PIN (10 alphanumeric chars)
    path = re.sub(r"/[A-Z0-9]{10}(?=/|$)", "/<pin>", path)
    # Numeric IDs
    path = re.sub(r"/\d+(?=/|$)", "/<id>", path)
    # Media download trailing path
    path = re.sub(r"(/media/download/).*", r"\1<path>", path)
    # ── Faza 4 (audit 2026-07-02): slug seqmentləri ──
    # Aşağıdakı qaydalar label kardinallığını imtahan/məqalə/təşkilat
    # SAYINDAN asılı olmaqdan çıxarır. Statik alt-səhifələr qorunur.
    # /exams/<slug>/… (statiklər: assigned, available, code-check, create,
    # groups, my-history, pending-work, question-bank)
    path = re.sub(
        r"(/exams/)(?!(?:assigned|available|code-check|create|groups|"
        r"my-history|pending-work|question-bank)(?:/|$))(?!<slug>)[^/]+",
        r"\1<slug>",
        path,
    )
    # Blog: /articles/<slug>/ və /categories/<slug>/
    path = re.sub(r"(/(?:articles|categories)/)[^/]+(?=/|$)", r"\1<slug>", path)
    # Təşkilatlar: /organizations/<slug>/… və /organizations/switch/<slug>/
    # (statik: select)
    path = re.sub(r"(/organizations/switch/)[^/]+(?=/|$)", r"\1<slug>", path)
    path = re.sub(
        r"(/organizations/)(?!(?:select|switch)(?:/|$))(?!<slug>)[^/]+",
        r"\1<slug>",
        path,
    )
    return path
