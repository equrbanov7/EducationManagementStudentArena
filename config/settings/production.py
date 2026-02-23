"""
Production settings for EMS Arena project.
Security-hardened configuration for production deployment.
"""

from __future__ import annotations

import os

import dj_database_url
import sentry_sdk
from dotenv import load_dotenv

from .base import BASE_DIR, STATICFILES_DIRS

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
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True") == "True"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"

# HSTS settings
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

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

# CSRF trusted origins
raw_csrf = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [x.strip() for x in raw_csrf.split(",") if x.strip()]

# Site URL
SITE_URL = os.getenv("SITE_URL", "https://emsarena.az")

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
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

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN", ""),
    send_default_pii=True,
)
