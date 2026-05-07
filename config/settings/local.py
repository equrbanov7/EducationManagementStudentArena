"""
Local settings for EMS Arena project.
Development environment configuration.
"""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

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
    DEFAULT_FROM_EMAIL,
    EMAIL_BACKEND,
    EMAIL_HOST,
    EMAIL_HOST_PASSWORD,
    EMAIL_HOST_USER,
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
    SITE_URL,
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
    _redis_url_with_db,
)

# Make mutable copies of lists inherited from base so that local-only
# additions (debug_toolbar, django_extensions) do not pollute the base module.
INSTALLED_APPS = list(INSTALLED_APPS)
MIDDLEWARE = list(MIDDLEWARE)
CHANNEL_LAYERS = deepcopy(CHANNEL_LAYERS)
CACHES = deepcopy(CACHES)


def _split_csv_env(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _env_bool(name: str, default: bool) -> bool:
    """Parse an environment variable as a boolean.

    Accepts: 1, true, yes, on  → True
             0, false, no, off → False
    Falls back to *default* when the variable is unset or empty.
    """
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# AI / Gemini configuration
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# SECURITY WARNING: SECRET_KEY must come from environment for local/dev too.
SECRET_KEY = (os.getenv("SECRET_KEY") or "").strip()
if not SECRET_KEY:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "\n"
        "SECRET_KEY is not set in your environment or .env file.\n"
        "The application cannot start without a secret key — this prevents\n"
        "session forgery and token tampering in any environment.\n\n"
        "Quick fix:\n"
        "  1. Create a .env file in the project root\n"
        '  2. Generate a key: python -c "import secrets; print(secrets.token_urlsafe(64))"\n'
        "  3. Set SECRET_KEY=<generated-key> in your .env file\n"
    )

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = _env_bool("DEBUG", True)
USE_REDIS = _env_bool("USE_REDIS", False)

# ALLOWED_HOSTS - read from .env or use default
ALLOWED_HOSTS = _split_csv_env("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0")
ENABLE_NGROK = os.getenv("ENABLE_NGROK", "False").lower() == "true"
if ENABLE_NGROK:
    ALLOWED_HOSTS.extend([".ngrok-free.dev", ".ngrok-free.app", ".ngrok.io", ".ngrok.app"])
ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS))

# Database - PostgreSQL with SQLite fallback for development
DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Recompute Redis-derived URLs after loading .env so local overrides take effect.
REDIS_URL = os.getenv("REDIS_URL", REDIS_URL).strip()
REDIS_CACHE_URL = _redis_url_with_db(REDIS_URL, 1)

if USE_REDIS:
    CHANNEL_LAYERS["default"] = {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    }
    CACHES["default"] = {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
    }
    CELERY_BROKER_URL = _redis_url_with_db(REDIS_URL, 2)
    CELERY_RESULT_BACKEND = CELERY_BROKER_URL
    CELERY_TASK_ALWAYS_EAGER = _env_bool("CELERY_TASK_ALWAYS_EAGER", False)
    CELERY_TASK_EAGER_PROPAGATES = _env_bool("CELERY_TASK_EAGER_PROPAGATES", False)
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "emsarena-local-cache",
        }
    }
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"
    CELERY_TASK_ALWAYS_EAGER = _env_bool("CELERY_TASK_ALWAYS_EAGER", True)
    CELERY_TASK_EAGER_PROPAGATES = _env_bool("CELERY_TASK_EAGER_PROPAGATES", True)

# Email backend:
# - If EMAIL_BACKEND is set explicitly, use it.
# - Otherwise, keep local/dev on the console backend by default so browser
#   testing and onboarding are not blocked by real SMTP quota/provider issues.
# - Opt into real SMTP locally with LOCAL_USE_SMTP_EMAIL=1.
LOCAL_USE_SMTP_EMAIL = _env_bool("LOCAL_USE_SMTP_EMAIL", False)
_resolved_local_email_user = (
    os.getenv("BREVO_SMTP_LOGIN") or os.getenv("BREVO_EMAIL") or os.getenv("EMAIL_HOST_USER", "")
)
_resolved_local_email_password = os.getenv("BREVO_SMTP_KEY") or os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    (
        "django.core.mail.backends.smtp.EmailBackend"
        if LOCAL_USE_SMTP_EMAIL and _resolved_local_email_user and _resolved_local_email_password
        else "django.core.mail.backends.console.EmailBackend"
    ),
)
EMAIL_HOST = os.getenv("EMAIL_HOST", EMAIL_HOST)
EMAIL_PORT = int(os.getenv("EMAIL_PORT", EMAIL_PORT))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", str(EMAIL_USE_TLS)).lower() in {"1", "true", "yes", "on"}
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", str(EMAIL_USE_SSL)).lower() in {"1", "true", "yes", "on"}
EMAIL_HOST_USER = (
    os.getenv("BREVO_SMTP_LOGIN") or os.getenv("BREVO_EMAIL") or os.getenv("EMAIL_HOST_USER", EMAIL_HOST_USER)
)
EMAIL_HOST_PASSWORD = os.getenv("BREVO_SMTP_KEY") or os.getenv("EMAIL_HOST_PASSWORD", EMAIL_HOST_PASSWORD)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or os.getenv("BREVO_FROM_EMAIL") or "no-reply@emsarena.com"

# Static files storage - Simple for development
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
# In local env, allow WhiteNoise to serve assets directly from finders.
# This prevents missing CSS/JS when DEBUG=False and collectstatic was not run.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
SERVE_MEDIA = True

# LAN host for development
LAN_HOST = os.getenv("LAN_HOST", "172.20.10.11:8000")
LIVE_EXAM_PUBLIC_HOST = os.getenv("LIVE_EXAM_PUBLIC_HOST", "")

# CSRF trusted origins
CSRF_TRUSTED_ORIGINS = _split_csv_env("CSRF_TRUSTED_ORIGINS")
if ENABLE_NGROK:
    CSRF_TRUSTED_ORIGINS.extend(
        [
            "https://*.ngrok-free.app",
            "http://*.ngrok-free.app",
            "https://*.ngrok-free.dev",
            "http://*.ngrok-free.dev",
            "https://*.ngrok.io",
            "http://*.ngrok.io",
            "https://*.ngrok.app",
            "http://*.ngrok.app",
        ]
    )
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(CSRF_TRUSTED_ORIGINS))

# Site URL for development
SITE_URL = os.getenv("SITE_URL", "http://172.20.10.11:8000")

# Add django-extensions for development (əgər paket qurulubsa)
try:
    import django_extensions  # noqa: F401

    INSTALLED_APPS.append("django_extensions")
except ImportError:
    pass

# Django Debug Toolbar (əgər paket qurulubsa)
if DEBUG:
    try:
        import debug_toolbar  # noqa: F401

        INSTALLED_APPS += ["debug_toolbar"]
        MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
        INTERNAL_IPS = ["172.20.10.11"]
    except ImportError:
        pass

# ==============================================================================
# LOGGING CONFIGURATION
# ==============================================================================

LOGS_DIR = BASE_DIR / "logs"

# Create logs directory if it doesn't exist
Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)

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
        "verbose": {
            "format": "[%(asctime)s] %(levelname)s [%(request_id)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
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
    },
}
