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
import sentry_sdk
from dotenv import load_dotenv

from .base import *


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
