"""Bitmiş TEST formatlı midterm cəhdlərinin balını jurnalın «Midterm» xanasına yazır (sahib 2026-10-21).

Yeni cəhdlər bitəndə avtomatik yazılır (``midterm_journal_sync``); bu komanda qaydadan ƏVVƏL bitmiş
cəhdlər üçün bir dəfəlik bərpadır. Yalnız SAYLAR çap olunur (ad / bal yoxdur — workflow loguna uyğun).

    manage.py sync_midterm_scores                 # DRY-RUN (defolt) — heç nə yazılmır
    manage.py sync_midterm_scores --org qku       # yalnız bu təşkilat (slug)
    manage.py sync_midterm_scores --org qku --apply

* Hər (tələbə, fənn) üçün yalnız RƏSMİ (ən son başlamış, bitmiş, sınaq olmayan) cəhd yazılır; qaydalar
  canlı körpü ilə EYNİDİR (gizli nəticə, sənədli düzəliş, bağlı jurnal, keçmiş dövr → atlanır).
* İdempotentdir: ikinci icra «dəyişməz» sayır; audit yalnız bal dəyişəndə; tələbəyə bildiriş GETMİR.
* Bütün DB işi ``rls_worker_atomic()`` + ``bypass_rls()`` içindədir; dry-run tranzaksiyası geri qaytarılır.
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.exams.models import ExamAttempt
from apps.exams.services import midterm_journal_sync
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class _DryRun(Exception):
    """Dry-run tranzaksiyasını geri qaytarmaq üçün."""


class Command(BaseCommand):
    help = "Bitmiş test formatlı midterm cəhdlərinin balını jurnalın Midterm xanasına yazır (defolt: dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="həqiqətən yaz (defolt: dry-run)")
        parser.add_argument("--org", default=None, help="yalnız bu təşkilatın slug-ı")

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        counts: Counter = Counter()
        with rls_worker_atomic(), bypass_rls():
            try:
                with transaction.atomic():
                    attempts = ExamAttempt.objects.all()
                    if options["org"]:
                        attempts = attempts.filter(exam__organization__slug=options["org"])
                    for attempt in midterm_journal_sync.official_attempts(attempts):
                        with transaction.atomic():
                            status, _row = midterm_journal_sync.sync_midterm_attempt(attempt, notify=False)
                        counts[status] += 1
                    if not apply:
                        raise _DryRun
            except _DryRun:
                pass
        mode = "YAZILDI" if apply else "DRY-RUN (heç nə yazılmadı — yazmaq üçün --apply)"
        total = sum(counts.values())
        parts = ", ".join(f"{status} {count}" for status, count in sorted(counts.items())) or "—"
        self.stdout.write(f"{mode}: rəsmi test midterm cəhdi {total}; {parts}")
