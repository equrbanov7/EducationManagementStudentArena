"""Oxşarlıq (plagiat) yoxlamasını yenidən işlədir — gözləyən/xətalı göndərişlər və ya bir tapşırıq.

İstifadə::

    python manage.py subject_folder_similarity                       # dry-run: neçə göndəriş
    python manage.py subject_folder_similarity --apply               # pending + failed
    python manage.py subject_folder_similarity --apply --task <uuid> # tapşırığın hamısı (yenidən)
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class Command(BaseCommand):
    help = "Fənn qovluğu: göndərişlərin oxşarlıq yoxlamasını (yenidən) işlədir."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Həqiqətən yoxla (default: dry-run).")
        parser.add_argument("--task", default="", help="Yalnız bu tapşırığın göndərişləri (hamısı yenidən).")
        parser.add_argument("--submission", default="", help="Yalnız bu göndəriş.")
        parser.add_argument("--limit", type=int, default=1000)

    def handle(self, *args, **options):
        from apps.subject_folder.constants import PlagiarismStatus, SubmissionStatus
        from apps.subject_folder.models import Submission
        from apps.subject_folder.services.plagiarism.engine import run_similarity_check

        with rls_worker_atomic(), bypass_rls():
            rows = Submission.objects.exclude(status=SubmissionStatus.DRAFT)
            if options["submission"]:
                rows = rows.filter(pk=options["submission"])
            elif options["task"]:
                rows = rows.filter(task_id=options["task"])
            else:
                rows = rows.filter(plagiarism_status__in=[PlagiarismStatus.PENDING, PlagiarismStatus.FAILED])
            ids = list(rows.order_by("submitted_at").values_list("pk", flat=True)[: max(1, options["limit"])])
            summary = {"candidates": len(ids), "flagged": 0, "failed": 0}
            if options["apply"]:
                for submission_id in ids:
                    result = run_similarity_check(submission_id)
                    summary["flagged"] += int(bool(result.get("flagged")))
                    summary["failed"] += int(result.get("status") == PlagiarismStatus.FAILED)
        mode = "APPLY" if options["apply"] else "DRY-RUN"
        self.stdout.write(f"[{mode}] {summary}")
