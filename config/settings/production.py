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
    CELERY_BEAT_SCHEDULE,
    CELERY_BROKER_URL,
    CELERY_RESULT_BACKEND,
    CELERY_RESULT_SERIALIZER,
    CELERY_TASK_SERIALIZER,
    CELERY_TASK_SOFT_TIME_LIMIT,
    CELERY_TASK_TIME_LIMIT,
    CELERY_TASK_TRACK_STARTED,
    CELERY_TIMEZONE,
    CHANNEL_LAYERS,
    CODING_EXECUTION_BACKEND,
    CODING_PISTON_AUTH_TOKEN,
    CODING_PISTON_URL,
    CODING_RUN_MAX_CONCURRENT_PER_USER,
    CODING_RUN_RATE_LIMIT_PER_MINUTE,
    CONTACT_NOTIFY_EMAIL,
    CONTACT_PUBLIC_EMAIL,
    CONTACT_SUPPORT_EMAIL,
    CONTENT_SECURITY_POLICY,
    CSRF_COOKIE_HTTPONLY,
    CSRF_COOKIE_SAMESITE,
    DEFAULT_AUTO_FIELD,
    EMAIL_BACKEND,
    EMAIL_HOST,
    EMAIL_PORT,
    EMAIL_USE_SSL,
    EMAIL_USE_TLS,
    EXAM_ANSWER_FILE_MAX_SIZE_MB,
    EXAM_ANSWER_MAX_FILES_PER_QUESTION,
    EXAM_AUTOSAVE_BINARY_UPLOADS_ENABLED,
    EXAM_AUTOSAVE_INTERVAL_MS,
    EXAM_AUTOSAVE_JITTER_MS,
    EXAM_PAINT_MAX_BASE64_CHARS,
    EXAM_RANDOMIZER_USAGE_CACHE_SECONDS,
    EXAM_START_GLOBAL_CONCURRENCY,
    EXAM_START_LOCK_LEASE_SECONDS,
    EXAM_START_PER_EXAM_CONCURRENCY,
    EXAM_START_POLL_INTERVAL_SECONDS,
    EXAM_START_WAIT_TIMEOUT_SECONDS,
    FILE_UPLOAD_SECURITY_MAX_SIZE_MB,
    HEALTH_CHECK_CACHE_SECONDS,
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
    METRICS_ALLOW_ANONYMOUS,
    MIDDLEWARE,
    OBJECT_STORAGE_ENABLED,
    OTP_RESEND_RATE_LIMIT,
    OTP_VERIFY_RATE_LIMIT,
    PASSWORD_RESET_TIMEOUT,
    POST_DELETE_RATE_LIMIT,
    RATELIMIT_ENABLE,
    RATELIMIT_USE_CACHE,
    REDIS_CACHE_URL,
    REDIS_URL,
    REQUEST_QUEUE_CACHE_ALIAS,
    REQUEST_QUEUE_ENABLED,
    REQUEST_QUEUE_EXCLUDED_PATH_PREFIXES,
    REQUEST_QUEUE_GLOBAL_UNSAFE_LIMIT,
    REQUEST_QUEUE_LOCAL_LOCK_TTL_SECONDS,
    REQUEST_QUEUE_LOCK_LEASE_SECONDS,
    REQUEST_QUEUE_LOCK_POLL_INTERVAL_SECONDS,
    REQUEST_QUEUE_PER_ACTOR_SERIALIZATION,
    REQUEST_QUEUE_RETRY_AFTER_SECONDS,
    REQUEST_QUEUE_UNSAFE_METHODS,
    REQUEST_QUEUE_WAIT_TIMEOUT_SECONDS,
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


def _env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _env_float(name: str, default: float, *, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


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

CONTACT_NOTIFY_EMAIL = os.getenv("CONTACT_NOTIFY_EMAIL") or CONTACT_NOTIFY_EMAIL
CONTACT_SUPPORT_EMAIL = os.getenv("CONTACT_SUPPORT_EMAIL") or CONTACT_SUPPORT_EMAIL
CONTACT_PUBLIC_EMAIL = os.getenv("CONTACT_PUBLIC_EMAIL") or CONTACT_PUBLIC_EMAIL
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
OBJECT_STORAGE_ENABLED = _env_bool("OBJECT_STORAGE_ENABLED", OBJECT_STORAGE_ENABLED)
METRICS_ALLOW_ANONYMOUS = _env_bool("METRICS_ALLOW_ANONYMOUS", METRICS_ALLOW_ANONYMOUS)

# SECURITY WARNING: Secret key must be set in environment
SECRET_KEY = os.environ["SECRET_KEY"]

# ---------------------------------------------------------------------------
# AI / Gemini configuration
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# SECURITY WARNING: Don't run with debug turned on in production!
DEBUG = False

# Heavy exam features are disabled in production to protect server resources.
# This keeps practical/coding exams, Piston-backed code execution, live
# supervision polling, WebSockets, and teacher-side lock controls off.
PRACTICAL_EXAMS_ENABLED = False
EXAM_SUPERVISION_ENABLED = False

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

# Database - PostgreSQL required for production. ASGI apps should avoid long
# lived Django DB connections; Daphne thread pools can otherwise exhaust
# Postgres after bursts of concurrent requests.
DATABASE_CONN_MAX_AGE = _env_int("DATABASE_CONN_MAX_AGE", 0, minimum=0)
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ["DATABASE_URL"],
        conn_max_age=DATABASE_CONN_MAX_AGE,
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

# Store sessions in Redis (read path) with DB durability (write path). Avoids a
# DB read on every authenticated request; combined with the throttled
# last_activity write this removes the per-request session DB write that
# bottlenecked login/auth under concurrent load. Redis is always present in
# production (cache, channels, celery, rate limiting all use it).
SESSION_ENGINE = os.getenv("SESSION_ENGINE", "django.contrib.sessions.backends.cached_db")
SESSION_CACHE_ALIAS = os.getenv("SESSION_CACHE_ALIAS", "default")
SESSION_ACTIVITY_WRITE_INTERVAL = int(os.getenv("SESSION_ACTIVITY_WRITE_INTERVAL", str(5 * 60)))

# HSTS settings
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000" if SECURE_SSL_REDIRECT else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", SECURE_HSTS_SECONDS > 0)
SECURE_HSTS_PRELOAD = _env_bool("SECURE_HSTS_PRELOAD", SECURE_HSTS_SECONDS > 0)

# Static files - WhiteNoise for production
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": STATICFILES_STORAGE,
    },
}

if OBJECT_STORAGE_ENABLED:
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
    AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "").strip()
    AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL", "").strip()
    AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "").strip()
    AWS_S3_CUSTOM_DOMAIN = os.getenv("AWS_S3_CUSTOM_DOMAIN", "").strip()
    AWS_S3_ADDRESSING_STYLE = os.getenv("AWS_S3_ADDRESSING_STYLE", "virtual").strip()
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = _env_bool("AWS_QUERYSTRING_AUTH", True)
    AWS_QUERYSTRING_EXPIRE = _env_int("AWS_QUERYSTRING_EXPIRE", 900, minimum=60)
    AWS_S3_OBJECT_PARAMETERS = {
        "CacheControl": os.getenv("AWS_S3_CACHE_CONTROL", "private, max-age=900"),
    }

    _missing_object_storage = [
        name
        for name, value in {
            "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
            "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
            "AWS_STORAGE_BUCKET_NAME": AWS_STORAGE_BUCKET_NAME,
            "AWS_S3_ENDPOINT_URL": AWS_S3_ENDPOINT_URL,
        }.items()
        if not value
    ]
    if _missing_object_storage:
        raise ImproperlyConfigured("OBJECT_STORAGE_ENABLED=true but missing: " + ", ".join(_missing_object_storage))

    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    }

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
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=sentry_dsn,
        send_default_pii=False,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
        environment=os.getenv("APP_ENV", "production"),
        release=os.getenv("APP_VERSION") or None,
        traces_sample_rate=_env_float("SENTRY_TRACES_SAMPLE_RATE", 0.05, minimum=0.0, maximum=1.0),
        profiles_sample_rate=_env_float("SENTRY_PROFILES_SAMPLE_RATE", 0.0, minimum=0.0, maximum=1.0),
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
