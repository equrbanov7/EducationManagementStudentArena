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


@app.on_after_configure.connect
def _register_retention_beat(sender, **kwargs):
    """AI köməkçisi jurnalının saxlama süpürgəsi (2026-09-14, audit F-08).

    Beat cədvəli ``CELERY_BEAT_SCHEDULE`` (settings) ilə gəlir; bu giriş konfiq
    yükləndikdən sonra ona əlavə olunur ki, iş adı ilə (import-suz) qeyd olunsun.
    Hər gecə 03:20 (``CELERY_TIMEZONE`` = Asia/Baku) — pik saatlardan kənar.
    """
    from celery.schedules import crontab

    # Celery `Settings` prefiksli açarı (`CELERY_BEAT_SCHEDULE`) `changes`
    # qatından ÖNCƏ tapır — yeni dict təyin etmək settings-dəki cədvəli əvəz
    # etmir. Ona görə mövcud lüğət YERİNDƏ dəyişdirilir; settings-də açar
    # yoxdursa (test) boş lüğət təyin olunur.
    schedule = sender.conf.beat_schedule
    if not isinstance(schedule, dict):
        schedule = {}
        sender.conf.beat_schedule = schedule
    schedule.setdefault(
        "ai-assistant-purge-logs",
        {"task": "ai_assistant.purge_logs", "schedule": crontab(hour=3, minute=20)},
    )
