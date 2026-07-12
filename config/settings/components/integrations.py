"""EMS Arena base settings — integrations komponenti.

Bu fayl `config/settings/base.py` tərəfindən paylaşılan namespace-də
`exec`-include olunur (django-split-settings üslubu). Ona görə burada
ayrıca import yoxdur — os, Path, messages, CSP sabitləri və `_env_*`
köməkçiləri base.py-dən gəlir. Sıra base.py-dəki _COMPONENTS siyahısı ilə
idarə olunur (asılılıqlar: bax base.py).
"""

# flake8: noqa: F821  (paylaşılan namespace: adlar base.py-dən gəlir)

# ---------------------------------------------------------------------------
# AI / Gemini configuration
# ---------------------------------------------------------------------------
# Google AI Studio / Gemini API key for AI-powered exam analytics summaries.
# Set via GEMINI_API_KEY environment variable.  When empty, the AI summary
# feature degrades gracefully (shows a "not configured" message).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ---------------------------------------------------------------------------
# Practical coding exam — sandbox execution backend
# ---------------------------------------------------------------------------
# Selects which executor runs student-submitted code for practical/coding
# exams. The Django process itself never executes the code.
#
#   - "docker" : run in local Docker (best isolation, requires daemon access).
#   - "piston" : forward to a Piston HTTP server (used by Render/Heroku/etc).
#   - "auto"   : prefer Docker when available, else fall back to Piston.
#   - "disabled" / "none": never execute submitted code.
#
# Default is "auto" so local-with-Docker dev keeps using Docker but production
# (where the Docker daemon is unreachable) automatically uses Piston instead
# of returning "Docker sandbox is not available on this server".
CODING_EXECUTION_BACKEND = os.getenv("CODING_EXECUTION_BACKEND", "auto").lower()

# Piston endpoint. Defaults to the public emkc.org instance; in production
# you should point this at a self-hosted instance to remove the public-API
# rate limit (≈5 req/s) and to keep student code on infrastructure you control.
CODING_PISTON_URL = os.getenv("CODING_PISTON_URL", "https://emkc.org/api/v2/piston")

# Optional Authorization header for protected (self-hosted) Piston instances.
# Leave empty for the public emkc.org instance, which does not require auth.
CODING_PISTON_AUTH_TOKEN = os.getenv("CODING_PISTON_AUTH_TOKEN", "")

# Classroom protection for the Run Code endpoint.
CODING_RUN_RATE_LIMIT_PER_MINUTE = os.getenv("CODING_RUN_RATE_LIMIT_PER_MINUTE", "120")
CODING_RUN_MAX_CONCURRENT_PER_USER = os.getenv("CODING_RUN_MAX_CONCURRENT_PER_USER", "2")

# Microsoft Clarity analytics. The project id is public by design; keep it
# overridable so staging/production can use different Clarity projects.
MICROSOFT_CLARITY_PROJECT_ID = os.getenv("MICROSOFT_CLARITY_PROJECT_ID", "x2xrg3vw2i").strip()

MICROSOFT_CLARITY_SCRIPT_SRC = (
    "https://www.clarity.ms",
    "https://*.clarity.ms",
)
MICROSOFT_CLARITY_CONNECT_SRC = (
    "https://www.clarity.ms",
    "https://*.clarity.ms",
    "https://c.bing.com",
)
MICROSOFT_CLARITY_IMG_SRC = (
    "https://*.clarity.ms",
    "https://c.bing.com",
)

# Message tags for toast notifications
MESSAGE_TAGS = {
    messages.DEBUG: "debug",
    messages.INFO: "info",
    messages.SUCCESS: "success",
    messages.WARNING: "warning",
    messages.ERROR: "danger",
}


# ---------------------------------------------------------------------------
# Sistem Monitorinqi (apps.monitoring) — backend-only asılılıq ünvanları.
# Bunlar YALNIZ daxili Docker şəbəkəsindəki servislərdir; heç vaxt frontend-ə
# ötürülmür. Boş/əlçatmaz olduqda API-lar "degraded" cavab qaytarır.
# ---------------------------------------------------------------------------
MONITORING_PROMETHEUS_URL = os.getenv("MONITORING_PROMETHEUS_URL", "http://prometheus:9090")
MONITORING_LOKI_URL = os.getenv("MONITORING_LOKI_URL", "http://loki:3100")
MONITORING_ALERTMANAGER_URL = os.getenv("MONITORING_ALERTMANAGER_URL", "http://alertmanager:9093")
# Alertmanager webhook-unun paylaşılan tokeni (docker-compose alertmanager
# servisi eyni dəyəri __WEBHOOK_TOKEN__ kimi alır). Boşdursa webhook bağlıdır.
ALERTMANAGER_WEBHOOK_TOKEN = os.getenv("ALERTMANAGER_WEBHOOK_TOKEN", "")
