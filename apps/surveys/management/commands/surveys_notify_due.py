"""Açılış günü gəlmiş dərc olunmuş sorğuların auditoriyasına in-app bildiriş (bir dəfə, idempotent).

Dərc anında açılış bu gündürsə bildiriş onsuz da gedir; bu əmr GƏLƏCƏK tarixli açılışlar üçündür
(cron / Celery beat ``surveys.notify_due_surveys`` ilə eyni iş)::

    python manage.py surveys_notify_due
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Vaxtı çatmış sorğu bildirişlərini göndərir (hər sorğu üçün bir dəfə)."

    def handle(self, *args, **options):
        from apps.surveys.services.survey_notify import notify_due

        with rls_worker_atomic(), bypass_rls():
            total = notify_due()
        self.stdout.write(f"notified recipients: {total}")
