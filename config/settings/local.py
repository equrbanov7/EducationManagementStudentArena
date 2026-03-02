"""
Local settings for EMS Arena project.
Development environment configuration.
"""

from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

from .base import *


def _split_csv_env(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# Ensure mutable copy (base-də tuple ola bilər)
STATICFILES_DIRS = list(STATICFILES_DIRS)

# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "django-insecure-g7=xgk^f!8x4871@^gsnvg0cl&)+@mug5+!j8%58dv2nt-#8xs",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", "True") == "True"

# ALLOWED_HOSTS - read from .env or use default
ALLOWED_HOSTS = _split_csv_env("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0")
ENABLE_NGROK = os.getenv("ENABLE_NGROK", "True").lower() == "true"
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

# Email backend:
# - If EMAIL_BACKEND is set explicitly, use it.
# - Otherwise, use SMTP when credentials exist; fallback to console backend.
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend"
    if os.getenv("EMAIL_HOST_USER") and os.getenv("EMAIL_HOST_PASSWORD")
    else "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", EMAIL_HOST)
EMAIL_PORT = int(os.getenv("EMAIL_PORT", EMAIL_PORT))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "False").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "True").lower() == "true"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL") or EMAIL_HOST_USER or "noreply@emsarena.local"

# Static files storage - Simple for development
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
# In local env, allow WhiteNoise to serve assets directly from finders.
# This prevents missing CSS/JS when DEBUG=False and collectstatic was not run.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

# Add live_exam static files directory for development
STATICFILES_DIRS.append(BASE_DIR / "apps" / "live_exam" / "static")

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

# (Səndə logging block kommentdədir — istəsən elə saxla)
