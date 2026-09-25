"""Müəllimlərə yeni göndərişlər xülasəsini göndərir (Celery beat yoxdursa cron ilə).

İstifadə::

    python manage.py subject_folder_digest            # dry-run: gözləyən göndəriş sayı
    python manage.py subject_folder_digest --apply    # intervalı nəzərə alaraq göndər
    python manage.py subject_folder_digest --apply --force
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Fənn qovluğu: müəllimlərə yeni göndərişlər xülasəsi."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--force", action="store_true", help="Son xülasədən interval keçməsə də göndər.")

    def handle(self, *args, **options):
        from apps.subject_folder.constants import SubmissionStatus
        from apps.subject_folder.models import Submission
        from apps.subject_folder.services.notify import send_submission_digests

        with rls_worker_atomic(), bypass_rls():
            pending = Submission.objects.filter(
                status=SubmissionStatus.SUBMITTED, is_current=True, teacher_notified_at__isnull=True
            ).count()
            sent = send_submission_digests(force=options["force"]) if options["apply"] else 0
        mode = "APPLY" if options["apply"] else "DRY-RUN"
        self.stdout.write(f"[{mode}] gözləyən göndəriş: {pending}; göndərilən xülasə: {sent}")
