"""İmtahandan UZAQLAŞDIRILMIŞ tələbələrin nəticəsi jurnalda 0 olsun (sahib 2026-11-16).

Sahib: «imtahandan uzaqlaşdırılmış, qovulmuş tələbələrin midterm nəticəsi ləğv olmalıdır, qeyd kimi də düşməlidir».
Canlı körpü qovulmanı artıq 0 bal kimi yazır, amma köhnə / atlanmış yazılar (bağlantı sonradan dəyişib, jurnal
gec açılıb və s.) qala bilər. Bu komanda ``supervision_status="removed"`` olan RƏSMİ cəhdləri (texniki
dayandırma YOX — yalnız uzaqlaşdırma və ləğv) canlı körpü ilə eyni yoldan yenidən yazır → jurnalda 0.
Tələbəyə qeyd nəticə səhifəsindədir (``interventions`` → «nəticəniz ləğv olunub»). Bildiriş GETMİR.

    manage.py annul_removed_exam_results_20261116 --org qku            # DRY-RUN (defolt)
    manage.py annul_removed_exam_results_20261116 --org qku --apply

Yalnız SAYLAR çap olunur: ``annul_removed: kind=… status=… n=…``. İdempotentdir (ikinci icra «unchanged»).
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.exams.models import ExamAttempt
from apps.exams.services import journal_sync, midterm_journal_sync
from apps.exams.services.supervision.interventions import attach_attempt_interventions
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class _DryRun(Exception):
    """Dry-run tranzaksiyasını geri qaytarmaq üçün."""


class Command(BaseCommand):
    help = "Uzaqlaşdırılmış (removed) tələbələrin rəsmi imtahan nəticəsini jurnalda 0 kimi yenidən yazır (dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="həqiqətən yaz (defolt: dry-run)")
        parser.add_argument("--org", default=None, help="yalnız bu təşkilatın slug-ı")

    def _attempts(self, org):
        attempts = (
            ExamAttempt.objects.filter(supervision_status="removed", finished_at__isnull=False, is_trial=False)
            .exclude(exam__subject_id__isnull=True)
            .select_related("exam", "exam__organization", "user")
            .order_by("pk")
        )
        if org:
            attempts = attempts.filter(exam__organization__slug=org)
        return attach_attempt_interventions(attempts)

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        counts: Counter = Counter()
        try:
            with rls_worker_atomic(), bypass_rls():
                try:
                    with transaction.atomic():
                        for attempt in self._attempts(options["org"]):
                            action = attempt.exam_intervention.get("action") or ""
                            if action not in ("removed", "annulled"):
                                counts[("skip", f"action_{action or 'none'}")] += 1
                                continue
                            with transaction.atomic():
                                if midterm_journal_sync.is_auto_midterm_exam(attempt.exam):
                                    kind = "midterm"
                                    status, _row = midterm_journal_sync.sync_midterm_attempt(attempt, notify=False)
                                else:
                                    kind = "final"
                                    status, _row = journal_sync.sync_final_attempt(attempt)
                            counts[(kind, str(status))] += 1
                        if not apply:
                            raise _DryRun
                except _DryRun:
                    pass
        except Exception as exc:  # prod-data-ops traceback göstərmir — kod adı ilə
            raise CommandError(f"annul_removed_failed: {type(exc).__name__}") from exc
        self.stdout.write(f"annul_removed: mode={'apply' if apply else 'dry_run'} total={sum(counts.values())}")
        for (kind, status), n in sorted(counts.items()):
            self.stdout.write(f"annul_removed: kind={kind} status={status} n={n}")
