"""
Local settings for EMS Arena project.
Development environment configuration.
"""

import os

import dj_database_url
from dotenv import load_dotenv

from .base import *  # noqa

# Load environment variables from .env file
load_dotenv(BASE_DIR / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv(
    "SECRET_KEY", "django-insecure-g7=xgk^f!8x4871@^gsnvg0cl&)+@mug5+!j8%58dv2nt-#8xs"
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", "True") == "True"

# ALLOWED_HOSTS - read from .env or use default
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0").split(",")

# Database - PostgreSQL with SQLite fallback for development
DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Email backend - Console for development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@emsarena.local")

# Static files storage - Simple for development
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Add live_exam static files directory for development
STATICFILES_DIRS.append(BASE_DIR / "apps" / "live_exam" / "static")

# LAN host for development
LAN_HOST = os.getenv("LAN_HOST", "127.0.0.1:8000")

# CSRF trusted origins
raw_csrf = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [x.strip() for x in raw_csrf.split(",") if x.strip()]

# Site URL for development
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")





# Add django-extensions for development if installed
try:
    import django_extensions  # noqa

    INSTALLED_APPS.append("django_extensions")
except ImportError:
    pass


# Django Debug Toolbar (varsa)
if DEBUG:
    try:
        import debug_toolbar
        INSTALLED_APPS += ['debug_toolbar']
        MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
        INTERNAL_IPS = ['127.0.0.1']
    except ImportError:
        pass


# ==============================================================================
# LOGGING CONFIGURATION
# ==============================================================================
# ==============================================================================
# LOGGING CONFIGURATION
# ==============================================================================

# Logs directory
LOGS_DIR = BASE_DIR / 'logs'

# Create logs directory if it doesn't exist
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# SUPER SADƏ - yalnız console, heç bir fayl
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,  # Köhnə logger-ları söndür
    'formatters': {
        'simple': {
            'format': '{levelname}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',  # Yalnız warning və error
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Autoreload noise-ı tamamilə söndür
        'django.utils.autoreload': {
            'handlers': [],
            'propagate': False,
        },
    },
}

# Logging - development üçün sadə
LOGGING['handlers']['console']['level'] = 'DEBUG'
LOGGING['loggers']['django']['level'] = 'DEBUG'