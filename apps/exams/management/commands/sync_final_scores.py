"""Bitmiş YEKUN (final) imtahan cəhdlərinin balını jurnala (``FinalGrade.exam_score``) yenidən yazır (sahib 2026-10-26).

Sahib: «İmtahan yaradarkən fənn seçirəm — tələbənin imtahan nəticəsi kimi sistemə düşəcəkmi? Bu hissə doğru
olsun.» Canlı körpü (``journal_sync.sync_final_attempt``) qeydiyyatı tapmayanda əvvəl SƏSSİZ no-op edirdi,
ehtiyat dövr seçimi gələcək semestrə düşə bilirdi, iki jurnallı tələbədə seçim təsadüfi idi. Qaydalar
düzəldikdən sonra bu əmr mövcud cəhdləri EYNİ yoldan təkrar keçirir (``midterm`` üçün ``sync_midterm_scores``
güzgüsü). Yalnız SAYLAR çap olunur (ad / bal yoxdur — workflow loguna uyğun).

    manage.py sync_final_scores                          # DRY-RUN (defolt) — heç nə yazılmır
    manage.py sync_final_scores --org qku                # yalnız bu təşkilat (slug)
    manage.py sync_final_scores --org qku --exam 123     # yalnız bu imtahan(lar) (id və ya slug, təkrarlana bilər)
    manage.py sync_final_scores --org qku --exam 123 --apply

Addımlar (hamısı bir tranzaksiyada; dry-run sonda geri qaytarılır):

1. **Bağlantı** — hər final imtahanın jurnal bağlantısı (``Exam.journal_offerings``) yenidən hesablanır
   (``exam_journal_link.refresh_links``) — körpü tələbənin balını bağlı jurnala yazır.
2. **Yazı** — hər (tələbə, fənn) üçün yalnız RƏSMİ (ən son başlamış, bitmiş, sınaq olmayan) final cəhdi
   ``sync_final_attempt`` ilə yazılır (25% cəhdi ``ResitRecord``-a, qeydiyyatı olmayan → ``no_enrollment``).

İdempotentdir: ``finals.set_exam_score`` audit izini yalnız bal DƏYİŞƏNDƏ yazır.
Bütün DB işi ``rls_worker_atomic()`` + ``bypass_rls()`` içindədir.
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import F, Q

from apps.exams.constants import ATTEMPT_FINISHED_STATUSES
from apps.exams.models import Exam, ExamAttempt
from apps.exams.services import exam_journal_link, journal_sync
from apps.exams.services.access_policy import FINAL_EXAM_CATEGORY
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


def official_final_attempts(queryset):
    """``queryset``-dəki bitmiş final cəhdlərindən (tələbə, fənn) üzrə RƏSMİ olanları (ən son başlamış)."""
    rows = (
        queryset.filter(
            exam__subject__isnull=False,
            exam__exam_type_extended=FINAL_EXAM_CATEGORY,
            exam__is_deleted=False,
            is_trial=False,
            status__in=ATTEMPT_FINISHED_STATUSES,
        )
        .select_related("exam", "exam__organization", "user")
        .order_by("user_id", "exam__subject_id", F("started_at").desc(nulls_last=True), "-pk")
    )
    seen = set()
    for attempt in rows.iterator(chunk_size=500):
        key = (attempt.user_id, attempt.exam.subject_id)
        if key in seen:
            continue
        seen.add(key)
        yield attempt


class Command(BaseCommand):
    help = (
        "Yekun (final) imtahan cəhdlərinin balını jurnala (FinalGrade) yenidən yazır və imtahanın jurnal "
        "bağlantısını yeniləyir (defolt: dry-run)."
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
            is_deleted=False, exam_type_extended=FINAL_EXAM_CATEGORY, subject__isnull=False
        ).select_related("organization", "journal_teacher")
        if options["org"]:
            exams = exams.filter(organization__slug=options["org"])
        if options["exam"]:
            exams = exams.filter(_exam_filter(options["exam"]))
            if not exams.exists():
                raise CommandError("Uyğun final imtahanı tapılmadı (--exam / --org).")
        return list(exams.order_by("pk"))

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        counts: Counter = Counter()
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
                    for attempt in official_final_attempts(attempts):
                        with transaction.atomic():
                            status, _row = journal_sync.sync_final_attempt(attempt)
                        counts[status] += 1
                    if not apply:
                        raise _DryRun
            except _DryRun:
                pass
        mode = "YAZILDI" if apply else "DRY-RUN (heç nə yazılmadı — yazmaq üçün --apply)"
        total = sum(counts.values())
        parts = ", ".join(f"{status} {count}" for status, count in sorted(counts.items())) or "—"
        self.stdout.write(
            f"{mode}: rəsmi final cəhdi {total}; {parts} | imtahan {len(exams)}, "
            f"jurnal bağlantısı yenilənən {relinked}"
        )
