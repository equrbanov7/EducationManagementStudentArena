"""
config/celery.py
────────────────
Celery application setup for EMS Arena.

The Celery app is wired into Django's settings via the ``CELERY_*`` keys
defined in ``config/settings/base.py``.  The broker and result backend both
use Redis (the same Redis instance already used for channel layers and caching,
but on a separate logical DB).

Usage
-----
Start a worker::

    celery -A config worker -l INFO

Start the beat scheduler (optional, for periodic tasks)::

    celery -A config beat -l INFO

Run both in development with a single command::

    celery -A config worker --beat -l INFO -S django
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("emsarena")

# Namespace all Celery config keys with ``CELERY_`` so they do not clash with
# other Django settings.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in each installed Django app (looks for tasks.py).
app.autodiscover_tasks()
