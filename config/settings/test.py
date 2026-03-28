"""
Test settings for EMS Arena project.
Fast, isolated configuration for running tests.
"""

import os

from django.core.management.utils import get_random_secret_key

import dj_database_url

from .base import (
    ASGI_APPLICATION,
    AUTH_OTP_EXPIRY_SECONDS,
    AUTH_PASSWORD_VALIDATORS,
    AUTHENTICATION_BACKENDS,
    BASE_DIR,
    CELERY_ACCEPT_CONTENT,
    CELERY_RESULT_SERIALIZER,
    CELERY_TASK_SERIALIZER,
    CELERY_TASK_SOFT_TIME_LIMIT,
    CELERY_TASK_TIME_LIMIT,
    CELERY_TASK_TRACK_STARTED,
    CELERY_TIMEZONE,
    CONTENT_SECURITY_POLICY,
    CSRF_COOKIE_HTTPONLY,
    CSRF_COOKIE_SAMESITE,
    DEFAULT_AUTO_FIELD,
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
    RATELIMIT_ENABLE,
    RATELIMIT_USE_CACHE,
    ROOT_URLCONF,
    SECURE_CONTENT_TYPE_NOSNIFF,
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

# Use environment secret for tests when provided; otherwise generate ephemeral key.
SECRET_KEY = os.getenv("SECRET_KEY") or get_random_secret_key()

# Debug should be False for tests to catch issues
DEBUG = False

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

# Use PostgreSQL for tests to match the production environment.
# The DATABASE_URL environment variable is set by the CI pipeline.
# For local development, fall back to a dedicated test database.
_DEFAULT_TEST_DB_URL = "postgres://localhost/test_emsarena"
DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv("DATABASE_URL", _DEFAULT_TEST_DB_URL),
        conn_max_age=0,
        conn_health_checks=False,
    )
}

# Use in-memory channel layer for tests
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

# Use MD5 password hasher for fast tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Use dummy cache for tests
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Use console email backend for tests
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
SITE_URL = "http://testserver"

# Celery — run tasks synchronously (eagerly) in tests so that no broker
# connection is required.  Email tasks will use the console backend above.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# Static files - simple storage for tests
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

# Disable migrations for faster tests (optional)
# class DisableMigrations:
#     def __contains__(self, item):
#         return True
#     def __getitem__(self, item):
#         return None
# MIGRATION_MODULES = DisableMigrations()
