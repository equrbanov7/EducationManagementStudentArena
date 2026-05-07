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
    "channels",
    "apps.live_exam",
    "apps.assignments",
    "apps.accounts.apps.AccountsConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.projects",
    "apps.labs",
    "apps.organizations.apps.OrganizationsConfig",
    "apps.audit.apps.AuditConfig",
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
# Practical/coding exams are still being hardened. Keep them available in
# local/test by default, but let production disable the feature explicitly.
PRACTICAL_EXAMS_ENABLED = os.getenv("PRACTICAL_EXAMS_ENABLED", "True").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
# Post management delete endpoints
POST_DELETE_RATE_LIMIT = os.getenv("POST_DELETE_RATE_LIMIT", "10/5m")
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
SECURITY_RESPONSE_HEADERS = {
    "Referrer-Policy": SECURE_REFERRER_POLICY,
    "Permissions-Policy": os.getenv(
        "PERMISSIONS_POLICY",
        "camera=(), geolocation=(), microphone=()",
    ),
    "Cross-Origin-Resource-Policy": os.getenv("CROSS_ORIGIN_RESOURCE_POLICY", "same-origin"),
    "Cross-Origin-Opener-Policy": os.getenv("CROSS_ORIGIN_OPENER_POLICY", "same-origin"),
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
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")

# ---------------------------------------------------------------------------
# AI / Gemini configuration
# ---------------------------------------------------------------------------
# Google AI Studio / Gemini API key for AI-powered exam analytics summaries.
# Set via GEMINI_API_KEY environment variable.  When empty, the AI summary
# feature degrades gracefully (shows a "not configured" message).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

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
