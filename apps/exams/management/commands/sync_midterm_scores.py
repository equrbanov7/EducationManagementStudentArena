"""Bitmiş TEST formatlı midterm cəhdlərinin balını jurnalın «Midterm» xanasına yazır (sahib 2026-10-21).

Yeni cəhdlər bitəndə avtomatik yazılır (``midterm_journal_sync``); bu komanda qaydadan ƏVVƏL bitmiş
cəhdlər və fənni / qrupları SONRADAN dəyişdirilmiş imtahanlar («JS Loop», 2026-10-24) üçün bərpadır.
Yalnız SAYLAR çap olunur (ad / bal yoxdur — workflow loguna uyğun).

    manage.py sync_midterm_scores                          # DRY-RUN (defolt) — heç nə yazılmır
    manage.py sync_midterm_scores --org qku                # yalnız bu təşkilat (slug)
    manage.py sync_midterm_scores --org qku --exam js-loop # yalnız bu imtahan(lar) (id və ya slug, təkrarlana bilər)
    manage.py sync_midterm_scores --org qku --exam js-loop --apply

Addımlar (hamısı bir tranzaksiyada; dry-run sonda geri qaytarılır):

1. **Bağlantı** — hər test midterminin jurnal bağlantısı (``Exam.journal_offerings``: fənn + qruplar üzrə hər
   qrupun öz açılışı) yenidən hesablanır (``exam_journal_link.refresh_links``).
2. **Yazı** — hər (tələbə, fənn) üçün yalnız RƏSMİ (ən son başlamış, bitmiş, sınaq olmayan) cəhd yazılır;
   qaydalar canlı körpü ilə EYNİDİR (gizli nəticə, sənədli düzəliş, bağlı jurnal, keçmiş dövr → atlanır).
3. **Təmizləmə** — imtahanın KÖHNƏ fənnin / jurnalın xanasına yazdığı avtomatik bal silinir (yalnız bu
   imtahanın yazdıqları; bağlanmış jurnal və sənədli düzəliş toxunulmur; hər silinmə auditlənir).

İdempotentdir: ikinci icra «dəyişməz» sayır; audit yalnız bal dəyişəndə; tələbəyə bildiriş GETMİR.
Bütün DB işi ``rls_worker_atomic()`` + ``bypass_rls()`` içindədir.
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.exams.models import Exam, ExamAttempt
from apps.exams.services import exam_journal_link, midterm_journal_sync
from apps.exams.services.journal_sync import MIDTERM_EXAM_CATEGORY
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic


class _DryRun(Exception):
    """Dry-run tranzaksiyasını geri qaytarmaq üçün."""


def _exam_filter(values) -> Q:
    query = Q()
    for value in values:
        value = str(value).strip()
        query |= Q(slug=value)
        if value.isdigit():
            query |= Q(pk=int(value))
    return query


class Command(BaseCommand):
    help = (
        "Test formatlı midterm cəhdlərinin balını jurnalın Midterm xanasına yazır, imtahanın jurnal "
        "bağlantısını yeniləyir və köhnə fənnin jurnalındakı avtomatik balı silir (defolt: dry-run)."
    )

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true", help="həqiqətən yaz (defolt: dry-run)")
        mode.add_argument("--dry-run", action="store_true", help="heç nə yazma, yalnız say (defolt)")
        parser.add_argument("--org", default=None, help="yalnız bu təşkilatın slug-ı")
        parser.add_argument(
            "--exam", action="append", default=[], help="yalnız bu imtahan (id və ya slug); təkrarlana bilər"
        )

    def _exams(self, options):
        exams = Exam.objects.filter(
            is_deleted=False,
            exam_type_extended=MIDTERM_EXAM_CATEGORY,
            exam_type=midterm_journal_sync.AUTO_MIDTERM_EXAM_TYPE,
        ).select_related("organization", "journal_teacher")
        if options["org"]:
            exams = exams.filter(organization__slug=options["org"])
        if options["exam"]:
            exams = exams.filter(_exam_filter(options["exam"]))
            if not exams.exists():
                raise CommandError("Uyğun test midterm imtahanı tapılmadı (--exam / --org).")
        return list(exams.order_by("pk"))

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        counts: Counter = Counter()
        cleanup: Counter = Counter()
        relinked = 0
        with rls_worker_atomic(), bypass_rls():
            try:
                with transaction.atomic():
                    exams = self._exams(options)
                    for exam in exams:
                        old_ids, new_ids = exam_journal_link.refresh_links(exam)
                        relinked += int(old_ids != new_ids)
                    attempts = ExamAttempt.objects.all()
                    if options["org"]:
                        attempts = attempts.filter(exam__organization__slug=options["org"])
                    if options["exam"]:
                        attempts = attempts.filter(exam__in=exams)
                    for attempt in midterm_journal_sync.official_attempts(attempts):
                        with transaction.atomic():
                            status, _row = midterm_journal_sync.sync_midterm_attempt(attempt, notify=False)
                        counts[status] += 1
                    for exam in exams:
                        cleanup.update(exam_journal_link.clear_stale(exam))
                    if not apply:
                        raise _DryRun
            except _DryRun:
                pass
        mode = "YAZILDI" if apply else "DRY-RUN (heç nə yazılmadı — yazmaq üçün --apply)"
        total = sum(counts.values())
        parts = ", ".join(f"{status} {count}" for status, count in sorted(counts.items())) or "—"
        cleaned = ", ".join(f"{status} {count}" for status, count in sorted(cleanup.items())) or "—"
        self.stdout.write(
            f"{mode}: rəsmi test midterm cəhdi {total}; {parts} | imtahan {len(exams)}, "
            f"jurnal bağlantısı yenilənən {relinked} | köhnə jurnal xanaları: {cleaned}"
        )
