"""EMS Arena base settings — admin_ratelimit komponenti.

Bu fayl `config/settings/base.py` tərəfindən paylaşılan namespace-də
`exec`-include olunur (django-split-settings üslubu). Ona görə burada
ayrıca import yoxdur — os, Path, messages, CSP sabitləri və `_env_*`
köməkçiləri base.py-dən gəlir. Sıra base.py-dəki _COMPONENTS siyahısı ilə
idarə olunur (asılılıqlar: bax base.py).
"""

# flake8: noqa: F821  (paylaşılan namespace: adlar base.py-dən gəlir)

# ---------------------------------------------------------------------------
# Admin security settings
# ---------------------------------------------------------------------------
# URL path segment for the Django admin panel.  Change this in production to
# avoid exposing the well-known /admin/ endpoint (set via ADMIN_URL_PREFIX
# environment variable).  The value must end with a slash.
ADMIN_URL_PREFIX = os.getenv("ADMIN_URL_PREFIX", "admin/")

# IP allowlist for admin access.  When non-empty, only requests from these
# addresses can reach the admin panel; all others receive HTTP 403.
# Set ADMIN_ALLOWED_IPS as a comma-separated list in the environment, e.g.:
#   ADMIN_ALLOWED_IPS=192.168.1.1,10.0.0.2
_raw_admin_ips = os.getenv("ADMIN_ALLOWED_IPS", "")
ADMIN_ALLOWED_IPS = [ip.strip() for ip in _raw_admin_ips.split(",") if ip.strip()]

# Rate limit for the admin login form (POST to /admin/login/).
# Accepts the same "count/period" format used by other rate limits.
ADMIN_LOGIN_RATE_LIMIT = os.getenv("ADMIN_LOGIN_RATE_LIMIT", "5/5m")
ADMIN_2FA_REQUIRED = os.getenv("ADMIN_2FA_REQUIRED", "False").strip().lower() in {"1", "true", "yes", "on"}
ADMIN_OTP_VERIFY_RATE_LIMIT = os.getenv("ADMIN_OTP_VERIFY_RATE_LIMIT", "5/10m")
ADMIN_OTP_RESEND_RATE_LIMIT = os.getenv("ADMIN_OTP_RESEND_RATE_LIMIT", "3/10m")

# Rate limiting configuration
RATELIMIT_ENABLE = True  # Can be set to False in development if needed
RATELIMIT_USE_CACHE = "default"
LOGIN_RATE_LIMIT = os.getenv("LOGIN_RATE_LIMIT", "5/10m")
OTP_VERIFY_RATE_LIMIT = os.getenv("OTP_VERIFY_RATE_LIMIT", "5/10m")
OTP_RESEND_RATE_LIMIT = os.getenv("OTP_RESEND_RATE_LIMIT", "3/10m")
SUBSCRIBE_RATE_LIMIT = os.getenv("SUBSCRIBE_RATE_LIMIT", "3/10m")
LIVE_EXAM_JOIN_RATE_LIMIT = os.getenv("LIVE_EXAM_JOIN_RATE_LIMIT", "20/5m")
LIVE_STATE_RATE_LIMIT = os.getenv("LIVE_STATE_RATE_LIMIT", "120/1m")
LIVE_REACTION_RATE_LIMIT = os.getenv("LIVE_REACTION_RATE_LIMIT", "3/10s")
# WebSocket-specific rate limits
LIVE_WS_CONNECT_RATE_LIMIT = os.getenv("LIVE_WS_CONNECT_RATE_LIMIT", "20/1m")
LIVE_ANSWER_RATE_LIMIT = os.getenv("LIVE_ANSWER_RATE_LIMIT", "10/1m")
LIVE_WS_MSG_RATE_LIMIT = os.getenv("LIVE_WS_MSG_RATE_LIMIT", "60/1m")
# AI per-user rate limit (protects shared Gemini API quota).
# Paid Tier 1: 10K RPD / 1K RPM on gemini-2.5-flash.  100 req/h is safe
# for a platform with <50 teachers sharing a $5/mo budget.
AI_RATE_LIMIT = os.getenv("AI_RATE_LIMIT", "100/1h")
AI_ASSISTANT_RATE_LIMIT = os.getenv("AI_ASSISTANT_RATE_LIMIT", "25/1h")
# Practical/coding exams are still being hardened. Keep them available in
# local/test by default, but let production disable the feature explicitly.
PRACTICAL_EXAMS_ENABLED = os.getenv("PRACTICAL_EXAMS_ENABLED", "True").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
EXAM_SUPERVISION_ENABLED = os.getenv("EXAM_SUPERVISION_ENABLED", "True").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
# Post management delete endpoints
POST_DELETE_RATE_LIMIT = os.getenv("POST_DELETE_RATE_LIMIT", "10/5m")
