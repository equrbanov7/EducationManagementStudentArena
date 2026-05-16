"""
Production settings for EMS Arena project.
Security-hardened configuration for production deployment.
"""

from __future__ import annotations

import os
from copy import deepcopy
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

import dj_database_url
from dotenv import load_dotenv

try:
    import sentry_sdk
except ModuleNotFoundError:  # pragma: no cover - optional in non-prod test envs
    sentry_sdk = None

from .base import (
    ADMIN_2FA_REQUIRED,
    ADMIN_ALLOWED_IPS,
    ADMIN_LOGIN_RATE_LIMIT,
    ADMIN_OTP_RESEND_RATE_LIMIT,
    ADMIN_OTP_VERIFY_RATE_LIMIT,
    ADMIN_URL_PREFIX,
    ASGI_APPLICATION,
    AUTH_OTP_EXPIRY_SECONDS,
    AUTH_PASSWORD_VALIDATORS,
    AUTHENTICATION_BACKENDS,
    BASE_DIR,
    CACHES,
    CELERY_ACCEPT_CONTENT,
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
    CELERY_RESULT_SERIALIZER,
    CELERY_TASK_SERIALIZER,
    CELERY_TASK_SOFT_TIME_LIMIT,
    CELERY_TASK_TIME_LIMIT,
    CELERY_TASK_TRACK_STARTED,
    CELERY_TIMEZONE,
    CHANNEL_LAYERS,
    CONTENT_SECURITY_POLICY,
    CSRF_COOKIE_HTTPONLY,
    CSRF_COOKIE_SAMESITE,
    DEFAULT_AUTO_FIELD,
    EMAIL_BACKEND,
    EMAIL_HOST,
    EMAIL_PORT,
    EMAIL_USE_SSL,
    EMAIL_USE_TLS,
    FILE_UPLOAD_SECURITY_MAX_SIZE_MB,
    INSTALLED_APPS,
    LANGUAGE_CODE,
    LANGUAGE_COOKIE_HTTPONLY,
    LANGUAGE_COOKIE_SAMESITE,
    LANGUAGES,
    LIVE_ANSWER_RATE_LIMIT,
    LIVE_EXAM_JOIN_RATE_LIMIT,
    LIVE_REACTION_RATE_LIMIT,
    LIVE_STATE_RATE_LIMIT,
    LIVE_WS_CONNECT_RATE_LIMIT,
    LIVE_WS_MSG_RATE_LIMIT,
    LOCALE_PATHS,
    LOGIN_RATE_LIMIT,
    LOGIN_REDIRECT_URL,
    LOGIN_URL,
    LOGOUT_REDIRECT_URL,
    MEDIA_ROOT,
    MEDIA_URL,
    MESSAGE_TAGS,
    MIDDLEWARE,
    OTP_RESEND_RATE_LIMIT,
    OTP_VERIFY_RATE_LIMIT,
    PASSWORD_RESET_TIMEOUT,
    POST_DELETE_RATE_LIMIT,
    RATELIMIT_ENABLE,
    RATELIMIT_USE_CACHE,
    REDIS_CACHE_URL,
    REDIS_URL,
    ROOT_URLCONF,
    SECURE_CONTENT_TYPE_NOSNIFF,
    SECURE_REFERRER_POLICY,
    SECURITY_RESPONSE_HEADERS,
    SERVE_MEDIA,
    SESSION_COOKIE_AGE,
    SESSION_COOKIE_HTTPONLY,
    SESSION_COOKIE_SAMESITE,
    SESSION_EXPIRE_AT_BROWSER_CLOSE,
    SESSION_INACTIVITY_TIMEOUT,
    STATIC_ROOT,
    STATIC_URL,
    STATICFILES_DIRS,
    SUBSCRIBE_RATE_LIMIT,
    TEMPLATES,
    TIME_ZONE,
    USE_I18N,
    USE_TZ,
    WHITENOISE_ALLOW_ALL_ORIGINS,
    WSGI_APPLICATION,
    X_FRAME_OPTIONS,
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _csp_connect_sources(*values: str) -> tuple[str, ...]:
    sources = {"'self'"}

    for value in values:
        raw = (value or "").strip()
        if not raw:
            continue

        if "://" not in raw:
            sources.add(f"https://{raw}")
            sources.add(f"wss://{raw}")
            continue

        parsed = urlsplit(raw)
        if not parsed.netloc:
            continue

        sources.add(f"{parsed.scheme}://{parsed.netloc}")
        if parsed.scheme == "https":
            sources.add(f"wss://{parsed.netloc}")
        elif parsed.scheme == "http":
            sources.add(f"ws://{parsed.netloc}")

    return tuple(sorted(sources))


# Load environment variables
load_dotenv(BASE_DIR / ".env")

# SECURITY WARNING: Secret key must be set in environment
SECRET_KEY = os.environ["SECRET_KEY"]

# ---------------------------------------------------------------------------
# AI / Gemini configuration
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# SECURITY WARNING: Don't run with debug turned on in production!
DEBUG = False

# Practical/coding exams must stay visible in production add/edit exam flows.
# Do not read this from the environment: a stale PRACTICAL_EXAMS_ENABLED=false
# value would hide the "coding" exam type from teacher forms.
PRACTICAL_EXAMS_ENABLED = True

ADMIN_URL_PREFIX = os.getenv("ADMIN_URL_PREFIX", "manage/")
if ADMIN_URL_PREFIX.strip("/").lower() == "admin":
    raise ImproperlyConfigured("ADMIN_URL_PREFIX must not expose the default /admin/ path in production.")

_raw_admin_ips = os.getenv("ADMIN_ALLOWED_IPS", "")
ADMIN_ALLOWED_IPS = [ip.strip() for ip in _raw_admin_ips.split(",") if ip.strip()]
# Empty ADMIN_ALLOWED_IPS disables the admin IP allowlist entirely. Keep the
# middleware behaviour aligned with base.py so production deploys can opt out
# when remote admins must sign in from changing IP addresses.

ADMIN_LOGIN_RATE_LIMIT = os.getenv("ADMIN_LOGIN_RATE_LIMIT", "3/15m")
ADMIN_2FA_REQUIRED = _env_bool("ADMIN_2FA_REQUIRED", True)
if not ADMIN_2FA_REQUIRED:
    raise ImproperlyConfigured("ADMIN_2FA_REQUIRED must remain enabled in production.")
ADMIN_OTP_VERIFY_RATE_LIMIT = os.getenv("ADMIN_OTP_VERIFY_RATE_LIMIT", "5/10m")
ADMIN_OTP_RESEND_RATE_LIMIT = os.getenv("ADMIN_OTP_RESEND_RATE_LIMIT", "3/10m")

# ALLOWED_HOSTS must be properly configured
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must not be empty in production settings.")

# Database - PostgreSQL required for production
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ["DATABASE_URL"],
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Security settings
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", True)
SESSION_COOKIE_HTTPONLY = _env_bool("SESSION_COOKIE_HTTPONLY", True)
CSRF_COOKIE_SECURE = _env_bool("CSRF_COOKIE_SECURE", True)
X_FRAME_OPTIONS = "DENY"

# Session timeout — tighter values in production for security.
# Absolute cookie lifetime: 1 day (overrides base.py default of 7 days).
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", str(1 * 24 * 60 * 60)))
# Inactivity timeout enforced by SessionTimeoutMiddleware: 8 hours.
SESSION_INACTIVITY_TIMEOUT = int(os.getenv("SESSION_INACTIVITY_TIMEOUT", str(8 * 60 * 60)))

# HSTS settings
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000" if SECURE_SSL_REDIRECT else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", SECURE_HSTS_SECONDS > 0)
SECURE_HSTS_PRELOAD = _env_bool("SECURE_HSTS_PRELOAD", SECURE_HSTS_SECONDS > 0)

# Static files - WhiteNoise for production
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Media files must not be served directly by Django in production.
# Configure your web server (nginx/caddy) to serve MEDIA_ROOT with appropriate
# access controls. Use the /media/download/<path>/ endpoint for authenticated access.
SERVE_MEDIA = False

# Nginx internal redirect prefix for X-Accel-Redirect (Task 6: private media).
# Nginx must define a matching `location /internal_media/ { internal; ... }` block.
MEDIA_ACCEL_REDIRECT_URL = os.getenv("MEDIA_ACCEL_REDIRECT_URL", "/internal_media")

# Email settings for production
# EMAIL_BACKEND can be overridden to use alternative providers:
#   django.core.mail.backends.smtp.EmailBackend   (default)
#   anymail.backends.sendgrid.EmailBackend         (SendGrid via django-anymail)
#   anymail.backends.amazon_ses.EmailBackend       (AWS SES via django-anymail)
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() in {"1", "true", "yes", "on"}
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").lower() in {"1", "true", "yes", "on"}
EMAIL_HOST_USER = os.getenv("BREVO_SMTP_LOGIN") or os.getenv("BREVO_EMAIL") or os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("BREVO_SMTP_KEY") or os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL") or os.getenv("BREVO_FROM_EMAIL") or "no-reply@emsarena.com"
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))  # seconds; avoids hanging workers

# LAN host
LAN_HOST = os.getenv("LAN_HOST", "emsarena.com")
LIVE_EXAM_PUBLIC_HOST = os.getenv("LIVE_EXAM_PUBLIC_HOST", "emsarena.com")

# CSRF trusted origins
raw_csrf = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [x.strip() for x in raw_csrf.split(",") if x.strip()]

# Site URL
SITE_URL = os.getenv("SITE_URL", "https://emsarena.com")

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "mask_sensitive": {
            "()": "core.logging_filters.SensitiveDataFilter",
        },
        "request_id": {
            "()": "core.logging_filters.RequestIdFilter",
        },
    },
    "formatters": {
        "json": {
            "()": "core.logging_filters.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["mask_sensitive", "request_id"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "django.core.mail": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "core.email_tasks": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

sentry_dsn = (os.getenv("SENTRY_DSN") or "").strip()
if sentry_dsn:
    if sentry_sdk is None:
        raise ImproperlyConfigured("SENTRY_DSN is set but sentry_sdk is not installed.")
    sentry_sdk.init(
        dsn=sentry_dsn,
        send_default_pii=False,
    )

# Content Security Policy (CSP) - Production overrides (stricter than base)
# Extends the base django-csp 4.0 dict with stricter production directives.
CONTENT_SECURITY_POLICY = deepcopy(CONTENT_SECURITY_POLICY)
CONTENT_SECURITY_POLICY["DIRECTIVES"].update(
    {
        "img-src": ["'self'", "data:", "blob:", "https:"],
        "media-src": ["'self'", "blob:", "https:"],
        "connect-src": list(_csp_connect_sources(SITE_URL, LIVE_EXAM_PUBLIC_HOST)),
        "frame-ancestors": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
    }
)
