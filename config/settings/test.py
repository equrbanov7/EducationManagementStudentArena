"""
Test settings for EMS Arena project.
Fast, isolated configuration for running tests.
"""

import os

import dj_database_url
from django.core.management.utils import get_random_secret_key

from .base import *  # noqa: F401,F403

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
