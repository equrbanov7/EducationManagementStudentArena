"""
Base settings for EMS Arena project.
Common settings shared across all environments.
"""

import os
from pathlib import Path

from django.contrib.messages import constants as messages

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
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "csp",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.accounts.middleware.SuspendedOrganizationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.organizations.middleware.OrganizationMiddleware",
    "csp.middleware.CSPMiddleware",
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
                "apps.organizations.context_processors.organization_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Channel Layers for WebSocket support
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

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
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "db": 1,  # Use database 1 for cache (0 is used by Channels)
        },
    }
}

# Rate limiting configuration
RATELIMIT_ENABLE = True  # Can be set to False in development if needed
RATELIMIT_USE_CACHE = "default"
LOGIN_RATE_LIMIT = os.getenv("LOGIN_RATE_LIMIT", "5/10m")
OTP_VERIFY_RATE_LIMIT = os.getenv("OTP_VERIFY_RATE_LIMIT", "5/10m")
OTP_RESEND_RATE_LIMIT = os.getenv("OTP_RESEND_RATE_LIMIT", "3/10m")
LIVE_EXAM_JOIN_RATE_LIMIT = os.getenv("LIVE_EXAM_JOIN_RATE_LIMIT", "20/5m")
LIVE_STATE_RATE_LIMIT = os.getenv("LIVE_STATE_RATE_LIMIT", "120/1m")
AUTH_OTP_EXPIRY_SECONDS = int(os.getenv("AUTH_OTP_EXPIRY_SECONDS", "180"))

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

# Keep CSRF cookie in Lax mode to reduce cross-site request risks on POST endpoints.
CSRF_COOKIE_SAMESITE = "Lax"

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

# Media files (Uploaded by users)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
SERVE_MEDIA = False
FILE_UPLOAD_SECURITY_MAX_SIZE_MB = int(os.getenv("FILE_UPLOAD_SECURITY_MAX_SIZE_MB", "25"))

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email base settings (to be overridden in environment-specific settings)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 465
EMAIL_USE_TLS = False
EMAIL_USE_SSL = True
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")

# Message tags for toast notifications
MESSAGE_TAGS = {
    messages.DEBUG: "debug",
    messages.INFO: "info",
    messages.SUCCESS: "success",
    messages.WARNING: "warning",
    messages.ERROR: "danger",
}

# Content Security Policy (CSP) settings
# XSS hücumlarına qarşı əlavə müdafiə təmin edir.
# Note: the current templates still rely on inline styles/scripts and CDN-hosted
# Bootstrap / Font Awesome assets, so the policy must explicitly allow them.
CSP_SCRIPT_SOURCES = (
    "'self'",
    "'unsafe-inline'",
    "https://cdn.jsdelivr.net",
    "https://cdnjs.cloudflare.com",
)
CSP_STYLE_SOURCES = (
    "'self'",
    "'unsafe-inline'",
    "https://fonts.googleapis.com",
    "https://cdn.jsdelivr.net",
    "https://cdnjs.cloudflare.com",
)
CSP_FONT_SOURCES = (
    "'self'",
    "data:",
    "https://fonts.gstatic.com",
    "https://cdnjs.cloudflare.com",
)

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        "script-src": CSP_SCRIPT_SOURCES,
        "style-src": CSP_STYLE_SOURCES,
        "img-src": ("'self'", "data:"),
        "font-src": CSP_FONT_SOURCES,
    }
}
