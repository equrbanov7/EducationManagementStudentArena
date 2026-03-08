"""
Test settings for EMS Arena project.
Fast, isolated configuration for running tests.
"""

import os

from django.core.management.utils import get_random_secret_key

from .base import *

# STATICFILES_DIRS bəzən tuple olur; append üçün list-ə çeviririk
STATICFILES_DIRS = list(STATICFILES_DIRS)

# Use environment secret for tests when provided; otherwise generate ephemeral key.
SECRET_KEY = os.getenv("SECRET_KEY") or get_random_secret_key()

# Debug should be False for tests to catch issues
DEBUG = False

# The local test environment may not have django-csp installed.
MIDDLEWARE = [mw for mw in MIDDLEWARE if mw != "csp.middleware.CSPMiddleware"]

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

# Use in-memory SQLite for fast tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
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

# Static files - simple storage for tests
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Add live_exam static files directory
STATICFILES_DIRS.append(BASE_DIR / "apps" / "live_exam" / "static")

# Disable migrations for faster tests (optional)
# class DisableMigrations:
#     def __contains__(self, item):
#         return True
#     def __getitem__(self, item):
#         return None
# MIGRATION_MODULES = DisableMigrations()
