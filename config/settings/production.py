"""
Production settings for EMS Arena project.
Security-hardened configuration for production deployment.
"""

from __future__ import annotations

import os

import dj_database_url
import sentry_sdk
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

from .base import *


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, str(default)).strip().lower()
    return value in {"1", "true", "yes", "on"}


# STATICFILES_DIRS base-də tuple ola bilər, append üçün list edirik
STATICFILES_DIRS = list(STATICFILES_DIRS)

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# SECURITY WARNING: Secret key must be set in environment
SECRET_KEY = os.environ["SECRET_KEY"]

# SECURITY WARNING: Don't run with debug turned on in production!
DEBUG = False

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

# HSTS settings
SECURE_HSTS_SECONDS = int(
    os.getenv("SECURE_HSTS_SECONDS", "31536000" if SECURE_SSL_REDIRECT else "0")
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", SECURE_HSTS_SECONDS > 0
)
SECURE_HSTS_PRELOAD = _env_bool("SECURE_HSTS_PRELOAD", SECURE_HSTS_SECONDS > 0)

# Static files - WhiteNoise for production
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Add live_exam static files directory
STATICFILES_DIRS.append(BASE_DIR / "apps" / "live_exam" / "static")

# Email settings for production
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@emsarena.az")

# LAN host
LAN_HOST = os.getenv("LAN_HOST", "emsarena.az")
LIVE_EXAM_PUBLIC_HOST = os.getenv("LIVE_EXAM_PUBLIC_HOST", "")

# CSRF trusted origins
raw_csrf = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [x.strip() for x in raw_csrf.split(",") if x.strip()]

# Site URL
SITE_URL = os.getenv("SITE_URL", "https://emsarena.az")

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "mask_sensitive": {
            "()": "core.logging_filters.SensitiveDataFilter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["mask_sensitive"],
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

sentry_dsn = (os.getenv("SENTRY_DSN") or "").strip()
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        send_default_pii=False,
    )

# Content Security Policy (CSP) - Production settings (daha ciddi)
# Base settings-dəki CSP-ni production üçün daha ciddi edirik
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        **CONTENT_SECURITY_POLICY["DIRECTIVES"],
        "script-src": CSP_SCRIPT_SOURCES,
        "style-src": CSP_STYLE_SOURCES,
        "img-src": ("'self'", "data:", "https:"),  # HTTPS-dən şəkil yükləməyə icazə
        "font-src": CSP_FONT_SOURCES,
        "connect-src": ("'self'",),  # AJAX/WebSocket bağlantıları
        "frame-ancestors": ("'none'",),  # Clickjacking-ə qarşı
        "base-uri": ("'self'",),  # Base tag-ı məhdudlaşdırır
        "form-action": ("'self'",),  # Form submission-ları məhdudlaşdırır
    }
}
