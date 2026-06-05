"""
Base settings for EMS Arena project.
Common settings shared across all environments.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from django.contrib.messages import constants as messages

from csp.constants import NONCE, NONE, SELF, UNSAFE_INLINE

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Application definition
INSTALLED_APPS = [
    "apps.courses.apps.CoursesConfig",
    "apps.blog",
    "apps.contact.apps.ContactConfig",
    "channels",
    "apps.live_exam",
    "apps.assignments",
    "apps.accounts.apps.AccountsConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.projects",
    "apps.labs",
    "apps.organizations.apps.OrganizationsConfig",
    "apps.audit.apps.AuditConfig",
    "apps.ai_assistant.apps.AIAssistantConfig",
    "daphne",
    "apps.exams",
    "core.admin_apps.SecureAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "csp",
]

MIDDLEWARE = [
    "core.middleware.RequestIdMiddleware",
    "core.middleware.MetricsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "csp.middleware.CSPMiddleware",
    "core.admin_security.AdminSecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.RequestQueueMiddleware",
    "apps.accounts.middleware.SessionTimeoutMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.accounts.middleware.PostLoginRedirectGuardMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.organizations.middleware.OrganizationMiddleware",
    "apps.accounts.middleware.SuspendedOrganizationMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.blog.context_processors.blog_navigation_context",
                "apps.organizations.context_processors.organization_context",
                "core.context_processors.seo_context",
                "core.context_processors.feature_flags",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


def _redis_url_with_db(redis_url: str, db: int) -> str:
    parsed = urlsplit(redis_url)
    if not parsed.scheme or not parsed.netloc:
        return redis_url

    path_parts = [part for part in parsed.path.split("/") if part]
    if path_parts and path_parts[-1].isdigit():
        path_parts[-1] = str(db)
    else:
        path_parts.append(str(db))

    return urlunsplit(parsed._replace(path="/" + "/".join(path_parts)))


# Channel Layers for WebSocket support
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip()
REDIS_CACHE_URL = _redis_url_with_db(REDIS_URL, 1)
CELERY_BROKER_URL = _redis_url_with_db(REDIS_URL, 2)

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

# Cache configuration (used for rate limiting and sessions)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
    }
}

# ─────────────────────────────────────────────────────────────────────────
# Celery — background task processing
# Broker: Redis DB 2  |  Results: Redis DB 2  |  Worker: see docker-compose
# ─────────────────────────────────────────────────────────────────────────
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Baku"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300  # 5 minutes hard limit per task
CELERY_TASK_SOFT_TIME_LIMIT = 240  # 4 minutes soft limit (raises SoftTimeLimitExceeded)

# Periodic tasks (require running `celery -A config beat`).
CELERY_BEAT_SCHEDULE = {
    # Auto-finish supervised attempts whose resume window elapsed without the
    # student returning.  Runs every minute so the supervision monitor never
    # shows stale open rows long after an exam has ended.
    "exams-expire-stale-resumed-attempts": {
        "task": "exams.expire_stale_resumed_attempts",
        "schedule": 60.0,  # seconds
    },
}

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


def _env_bool_setting(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_int_setting(name: str, default: int, *, minimum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _env_float_setting(name: str, default: float, *, minimum: float | None = None) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


# Student exam autosave is intentionally slow on the server side. Answers are
# still written to browser localStorage immediately, while DB writes are batched.
EXAM_AUTOSAVE_INTERVAL_MS = _env_int_setting("EXAM_AUTOSAVE_INTERVAL_MS", 300_000, minimum=60_000)
EXAM_AUTOSAVE_JITTER_MS = _env_int_setting("EXAM_AUTOSAVE_JITTER_MS", 60_000, minimum=0)
EXAM_AUTOSAVE_BINARY_UPLOADS_ENABLED = _env_bool_setting("EXAM_AUTOSAVE_BINARY_UPLOADS_ENABLED", False)

# Written-answer uploads are accepted on explicit save/submit, but kept tight
# so a single student cannot push large multipart or canvas payloads repeatedly.
EXAM_ANSWER_FILE_MAX_SIZE_MB = _env_int_setting("EXAM_ANSWER_FILE_MAX_SIZE_MB", 5, minimum=1)
EXAM_ANSWER_MAX_FILES_PER_QUESTION = _env_int_setting("EXAM_ANSWER_MAX_FILES_PER_QUESTION", 3, minimum=1)
EXAM_PAINT_MAX_BASE64_CHARS = _env_int_setting("EXAM_PAINT_MAX_BASE64_CHARS", 1_500_000, minimum=100_000)
EXAM_START_GLOBAL_CONCURRENCY = _env_int_setting("EXAM_START_GLOBAL_CONCURRENCY", 12, minimum=0)
EXAM_START_PER_EXAM_CONCURRENCY = _env_int_setting("EXAM_START_PER_EXAM_CONCURRENCY", 6, minimum=0)
EXAM_START_WAIT_TIMEOUT_SECONDS = _env_float_setting("EXAM_START_WAIT_TIMEOUT_SECONDS", 30.0, minimum=0.0)
EXAM_START_POLL_INTERVAL_SECONDS = _env_float_setting("EXAM_START_POLL_INTERVAL_SECONDS", 0.05, minimum=0.01)
EXAM_START_LOCK_LEASE_SECONDS = _env_int_setting("EXAM_START_LOCK_LEASE_SECONDS", 120, minimum=1)
EXAM_RANDOMIZER_USAGE_CACHE_SECONDS = _env_int_setting("EXAM_RANDOMIZER_USAGE_CACHE_SECONDS", 30, minimum=0)


# Request queueing for mutating HTTP calls. This protects every app view from
# duplicate/bursty writes by serialising unsafe methods per user/session and by
# limiting concurrent write requests per worker process.
# Set REQUEST_QUEUE_GLOBAL_UNSAFE_LIMIT=1 if deployment needs strict
# one-write-at-a-time behaviour.
REQUEST_QUEUE_ENABLED = _env_bool_setting("REQUEST_QUEUE_ENABLED", True)
REQUEST_QUEUE_UNSAFE_METHODS = tuple(
    method.strip().upper()
    for method in os.getenv("REQUEST_QUEUE_UNSAFE_METHODS", "POST,PUT,PATCH,DELETE").split(",")
    if method.strip()
)
REQUEST_QUEUE_PER_ACTOR_SERIALIZATION = _env_bool_setting("REQUEST_QUEUE_PER_ACTOR_SERIALIZATION", True)
REQUEST_QUEUE_GLOBAL_UNSAFE_LIMIT = _env_int_setting("REQUEST_QUEUE_GLOBAL_UNSAFE_LIMIT", 8, minimum=0)
REQUEST_QUEUE_WAIT_TIMEOUT_SECONDS = _env_float_setting("REQUEST_QUEUE_WAIT_TIMEOUT_SECONDS", 60.0, minimum=0.0)
REQUEST_QUEUE_LOCK_POLL_INTERVAL_SECONDS = _env_float_setting(
    "REQUEST_QUEUE_LOCK_POLL_INTERVAL_SECONDS",
    0.05,
    minimum=0.01,
)
REQUEST_QUEUE_LOCK_LEASE_SECONDS = _env_int_setting("REQUEST_QUEUE_LOCK_LEASE_SECONDS", 600, minimum=1)
REQUEST_QUEUE_LOCAL_LOCK_TTL_SECONDS = _env_int_setting("REQUEST_QUEUE_LOCAL_LOCK_TTL_SECONDS", 300, minimum=1)
REQUEST_QUEUE_RETRY_AFTER_SECONDS = _env_int_setting("REQUEST_QUEUE_RETRY_AFTER_SECONDS", 2, minimum=1)
REQUEST_QUEUE_CACHE_ALIAS = os.getenv("REQUEST_QUEUE_CACHE_ALIAS", RATELIMIT_USE_CACHE)
# NOTE: Authentication / onboarding POST endpoints are intentionally excluded
# from the request queue. They are unauthenticated (so the per-actor lock keys
# every visitor behind a shared proxy IP onto the SAME lock, serialising all
# logins) and they must never be gated by the global write-concurrency
# semaphore — otherwise concurrent logins queue up to
# REQUEST_QUEUE_WAIT_TIMEOUT_SECONDS and time out under load. Authenticated
# mutating /accounts/ endpoints (profile, role/org management) are NOT listed
# here, so they keep their double-submit protection.
REQUEST_QUEUE_EXCLUDED_PATH_PREFIXES = tuple(
    prefix.strip()
    for prefix in os.getenv(
        "REQUEST_QUEUE_EXCLUDED_PATH_PREFIXES",
        (
            "/static/,/media/,/metrics/,/ping/,/health/,"
            "/accounts/login/,/accounts/register/,/accounts/verify-code/,"
            "/accounts/resend-code/,/accounts/send-otp/,/accounts/verify-otp/,"
            "/accounts/resend-otp/,/accounts/password-reset/,/accounts/reset/"
        ),
    ).split(",")
    if prefix.strip()
)
HEALTH_CHECK_CACHE_SECONDS = _env_float_setting("HEALTH_CHECK_CACHE_SECONDS", 2.0, minimum=0.0)
AUTH_OTP_EXPIRY_SECONDS = int(os.getenv("AUTH_OTP_EXPIRY_SECONDS", "300"))
AUTH_OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("AUTH_OTP_RESEND_COOLDOWN_SECONDS", "60"))
AUTH_OTP_MAX_ATTEMPTS = int(os.getenv("AUTH_OTP_MAX_ATTEMPTS", "5"))
AUTH_OTP_MAX_SENDS_PER_HOUR = int(os.getenv("AUTH_OTP_MAX_SENDS_PER_HOUR", "5"))
AUTH_PENDING_SIGNUP_TTL_SECONDS = int(os.getenv("AUTH_PENDING_SIGNUP_TTL_SECONDS", "86400"))

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Login / logout settings
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# ---------------------------------------------------------------------------
# Session timeout settings
# ---------------------------------------------------------------------------
# Absolute lifetime of the session cookie (seconds).  After this period the
# browser discards the cookie and the user must log in again regardless of
# activity.  Default: 7 days.
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", str(7 * 24 * 60 * 60)))

# Expire the session cookie when the browser is closed (no persistent cookie).
# Set to True for higher-security deployments; False keeps the cookie across
# browser restarts up to SESSION_COOKIE_AGE.
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Inactivity timeout enforced by SessionTimeoutMiddleware (seconds).
# Users who have not made any request within this window are automatically
# logged out on their next request, even if SESSION_COOKIE_AGE has not yet
# elapsed.  Default: 3 days.
SESSION_INACTIVITY_TIMEOUT = int(os.getenv("SESSION_INACTIVITY_TIMEOUT", str(3 * 24 * 60 * 60)))

# ---------------------------------------------------------------------------
# Session storage backend (performance)
# ---------------------------------------------------------------------------
# Default to ``cached_db``: session reads are served from Redis (no DB hit on
# every authenticated request) while writes still persist to the DB so a Redis
# restart does not log everyone out mid-exam. Combined with the throttled
# ``last_activity`` write in SessionTimeoutMiddleware (see below), this removes
# the per-request session write that previously serialised authenticated
# traffic on the database under load. Override with SESSION_ENGINE=... if a
# deployment prefers pure-cache or pure-db sessions.
SESSION_ENGINE = os.getenv("SESSION_ENGINE", "django.contrib.sessions.backends.cached_db")
SESSION_CACHE_ALIAS = os.getenv("SESSION_CACHE_ALIAS", "default")

# SessionTimeoutMiddleware records the last activity timestamp on the session.
# Writing it on EVERY request marks the session dirty and forces a save (and a
# DB write under cached_db/db) on every hit. Instead we only persist the
# timestamp once per this interval; inactivity is still enforced accurately
# because the stored value is at most this many seconds stale relative to the
# multi-hour inactivity timeout. Default: 5 minutes.
SESSION_ACTIVITY_WRITE_INTERVAL = int(os.getenv("SESSION_ACTIVITY_WRITE_INTERVAL", str(5 * 60)))

# ---------------------------------------------------------------------------
# Cookie security settings
# ---------------------------------------------------------------------------
# Session cookie: HttpOnly prevents JS access; Lax blocks cross-site POST.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

# CSRF cookie: SameSite=Lax protects against CSRF on cross-site requests.
# HttpOnly must be False so the JS CSRF helper can read the token.
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"

# Language cookie: HttpOnly and SameSite to protect the i18n cookie
# set by /i18n/setlang/.
LANGUAGE_COOKIE_HTTPONLY = True
LANGUAGE_COOKIE_SAMESITE = "Lax"

# ---------------------------------------------------------------------------
# Security headers (apply to all environments; stricter values in production)
# ---------------------------------------------------------------------------
# Prevent the browser from MIME-sniffing a response away from the declared
# content-type.
SECURE_CONTENT_TYPE_NOSNIFF = True

# Instruct browsers not to render this site inside a frame (clickjacking).
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = os.getenv("REFERRER_POLICY", "strict-origin-when-cross-origin")

# Additional response headers that tighten browser-side defaults without
# requiring per-view duplication.
#
# An env var set to an empty string ("") removes the header — useful in HTTP
# dev where browsers ignore the COOP header anyway and only emit a noisy
# console warning ("origin was untrustworthy"). Production must always send
# the header, so we keep "same-origin" as the default.
SECURITY_RESPONSE_HEADERS = {
    k: v
    for k, v in {
        "Referrer-Policy": SECURE_REFERRER_POLICY,
        "Permissions-Policy": os.getenv(
            "PERMISSIONS_POLICY",
            "camera=(), geolocation=(), microphone=()",
        ),
        "Cross-Origin-Resource-Policy": os.getenv("CROSS_ORIGIN_RESOURCE_POLICY", "same-origin"),
        "Cross-Origin-Opener-Policy": os.getenv("CROSS_ORIGIN_OPENER_POLICY", "same-origin"),
    }.items()
    if v
}

# Authentication backends
AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailOrUsernameBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Password reset token expiry defaults to the same short-lived OTP window.
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT", str(AUTH_OTP_EXPIRY_SECONDS)))

# Internationalization
LANGUAGE_CODE = "az"
LANGUAGES = [
    ("az", "Azərbaycan dili"),
    ("en", "English"),
    ("ru", "Русский"),
    ("tr", "Türkçe"),
]
LOCALE_PATHS = [
    BASE_DIR / "locale",
]
TIME_ZONE = "Asia/Baku"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
# WhiteNoise adds a wildcard ACAO header by default; keep static assets same-origin
# unless cross-origin delivery is explicitly configured at the edge.
WHITENOISE_ALLOW_ALL_ORIGINS = False

# Media files (Uploaded by users)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
SERVE_MEDIA = False
FILE_UPLOAD_SECURITY_MAX_SIZE_MB = int(os.getenv("FILE_UPLOAD_SECURITY_MAX_SIZE_MB", "25"))
OBJECT_STORAGE_ENABLED = _env_bool_setting("OBJECT_STORAGE_ENABLED", False)
METRICS_ALLOW_ANONYMOUS = _env_bool_setting("METRICS_ALLOW_ANONYMOUS", False)

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email base settings (to be overridden in environment-specific settings)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() in {"1", "true", "yes", "on"}
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").lower() in {"1", "true", "yes", "on"}
EMAIL_HOST_USER = os.getenv("BREVO_SMTP_LOGIN") or os.getenv("BREVO_EMAIL") or os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("BREVO_SMTP_KEY") or os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or os.getenv("BREVO_FROM_EMAIL") or "no-reply@emsarena.com"
# SMTP socket timeout. Kept low so the request thread (or even background
# threads) cannot stall on an unresponsive SMTP host. Override via env if
# the upstream server is known-slow.
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "8"))
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")

# ---------------------------------------------------------------------------
# Contact form notifications
# ---------------------------------------------------------------------------
# Inbound public contact form submissions are delivered to this address.
# Brevo has the following verified senders for emsarena.com:
#   - support@emsarena.com  (technical / dispatch inbox)
#   - info@emsarena.com     (general info & contact form recipient)
#   - no-reply@emsarena.com (system / transactional sender)
# Override via ``CONTACT_NOTIFY_EMAIL`` env var in production.
CONTACT_NOTIFY_EMAIL = os.getenv("CONTACT_NOTIFY_EMAIL", "info@emsarena.com")
CONTACT_SUPPORT_EMAIL = os.getenv("CONTACT_SUPPORT_EMAIL", "support@emsarena.com")
CONTACT_PUBLIC_EMAIL = os.getenv("CONTACT_PUBLIC_EMAIL", "info@emsarena.com")

# Brevo (formerly Sendinblue) HTTP API key. Used as a fallback when SMTP
# fails (e.g., ISP blocks port 587). Generated in Brevo dashboard:
# Settings → SMTP & API → API Keys. Port 443 / HTTPS bypasses every
# port-blocking middlebox so this is the most reliable transport.
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")

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

# Message tags for toast notifications
MESSAGE_TAGS = {
    messages.DEBUG: "debug",
    messages.INFO: "info",
    messages.SUCCESS: "success",
    messages.WARNING: "warning",
    messages.ERROR: "danger",
}

# Content Security Policy (CSP) settings
# https://django-csp.readthedocs.io/en/latest/configuration.html
#
# 'unsafe-inline' is intentionally absent from script-src.
# Inline <script> blocks must use a per-request nonce
# via {{ request.csp_nonce }} and the NONCE sentinel.
#
# Inline <style> blocks must also use a per-request nonce. Inline style=""
# attributes are temporarily scoped to style-src-attr so style-src itself can
# remain strict while the remaining templates are migrated off inline attrs.
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": [SELF],
        "font-src": [
            SELF,
            "data:",
            "https://fonts.gstatic.com",
        ],
        "img-src": [
            SELF,
            "data:",
            "blob:",
        ],
        "media-src": [
            SELF,
            "blob:",
        ],
        "script-src": [
            SELF,
            NONCE,
        ],
        "style-src": [
            SELF,
            NONCE,
            "https://fonts.googleapis.com",
        ],
        "style-src-attr": [
            UNSAFE_INLINE,
        ],
        "connect-src": [
            SELF,
            "ws://127.0.0.1:8000",
            "ws://localhost:8000",
            "ws://0.0.0.0:8000",
        ],
        "object-src": [NONE],
        "base-uri": [SELF],
        "frame-ancestors": [NONE],
        "form-action": [SELF],
    }
}
