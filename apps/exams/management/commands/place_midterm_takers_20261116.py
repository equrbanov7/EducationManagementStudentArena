"""Midterm nəticəsi olan, amma fənnin jurnalında OLMAYAN tələbəni jurnala sal + balını yaz (sahib 2026-11-16).

Sahib: «119 tələbəni də jurnala sal … həmin fəndən jurnalı yoxdursa deməli alt qrupdur, alt qrup kimi əlavə et …
midterm nəticəsi olan tələbə o deməkdir ki o fənni oxuyur … 2 nəticə varsa yuxarı olanını götür» və «hansı qrupa salmaq
sualı yaranırsa, verdiyi saatda hansı qrup imtahan veribsə o qrupdadır».

Hər cari dövr RƏSMİ midterm cəhdi (2 nəticədə YÜKSƏK olanı — ``midterm_journal_sync.attempt_rank``) canlı körpü ilə
yazılır; körpü jurnal tapmırsa (``no_enrollment``) səbəbə görə (``registrar.exam_result_gaps``):

* ``dropped`` — fənnin cari jurnalından çıxarılıb → jurnal səhifəsinin «Bərpa et» yolu (``journal_roster_restore``);
* tək hədəf (öz qrupu / alt qrup / imtahan qrupunun jurnalı) → ``exam_taker_placement_2026_11_11.place``
  (öz qrupuna adi sətir, başqa qrupa rəsmi «alt qrup tələbəsi» — sənədsiz, superadmin keçidi);
* bir neçə jurnal → EYNİ imtahanı EYNİ oturumda (bilet oturumu; yoxdursa ±60 dəq.) verənlərin jurnalı
  (``cotaker_offering``) seçilir və eyni yolla əlavə olunur; bölünmüşdürsə yazılmır (sayılır);
* oxşar adlı kart (``variant_subject``), Kollec, aktiv qeydi olmayan — yazılmır, sayılır.

İmtahandan UZAQLAŞDIRILMIŞ cəhd (bilet ``removed`` / ``supervision_status=removed``) toxunulmur — ayrıca sayılır
(ləğv başqa addımdadır). Yerləşdirmə + bərpa sətirləri ``dupsubj-…`` paketinə yazılır — geri qaytarma:
``merge_duplicate_subjects_20261111 --undo --batch dupsubj-…`` (toxunulmamış sətirlər). DEFOLT DRY-RUN; bildiriş
yoxdur; stdout-a YALNIZ saylar + imtahan id-si.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.exams.models import Exam, ExamAttempt
from apps.exams.services import exam_journal_link, midterm_journal_sync
from apps.exams.services.journal_sync import MIDTERM_EXAM_CATEGORY
from apps.organizations.models import Organization
from apps.registrar.public import duplicate_subjects_2026_11_11 as duplicates
from apps.registrar.public import exam_journal_gaps
from apps.registrar.public import exam_journal_link as registrar_link
from apps.registrar.public import exam_taker_placement_2026_11_11 as placement
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "midterm_takers:"
NO_ENROLLMENT = "no_enrollment"
WINDOW = timedelta(minutes=60)


class _DryRun(Exception):
    """Dry-run tranzaksiyasını geri qaytarmaq üçün."""


class Command(BaseCommand):
    help = "Midterm nəticəsi olan, jurnalı olmayan tələbəni jurnala sal və balını yaz (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True)
        parser.add_argument("--actor", required=True, help="aktiv superadmin istifadəçi adı")
        parser.add_argument("--apply", action="store_true", help="həqiqətən yaz (defolt: dry-run)")

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        self.counts: Counter = Counter()
        self.by_exam: Counter = Counter()
        self.batch = ""
        try:
            with rls_worker_atomic(), bypass_rls():
                organization = Organization.objects.filter(slug=str(options["org"]).strip()).first()
                if organization is None:
                    raise CommandError("organization_not_found")
                actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
                if actor is None or not actor.is_superuser:
                    raise CommandError("actor_must_be_active_superuser")
                period = registrar_link.current_period(organization)
                if period is None:
                    raise CommandError("current_period_missing")
                self.batch = duplicates.new_batch_id()
                try:
                    with transaction.atomic():
                        self._run(organization, period, actor)
                        if not apply:
                            raise _DryRun
                except _DryRun:
                    pass
        except CommandError:
            raise
        except Exception as exc:  # prod-data-ops traceback-i gizlədir — kod görünsün
            raise CommandError(f"takers_failed_{type(exc).__name__.lower()}") from exc
        self._report(apply)

    def _run(self, organization, period, actor) -> None:
        exams = Exam.objects.filter(
            organization=organization,
            is_deleted=False,
            subject__isnull=False,
            exam_type_extended=MIDTERM_EXAM_CATEGORY,
            exam_type__in=midterm_journal_sync.AUTO_MIDTERM_EXAM_TYPES,
        ).select_related("organization", "journal_teacher")
        for exam in exams:
            exam_journal_link.refresh_links(exam)
        student_gaps = exam_journal_gaps.student_gaps
        self.ctx = student_gaps.context(organization, period)
        self.units: dict = {}
        receipts = []
        rows = ExamAttempt.objects.filter(exam__organization=organization, started_at__date__gte=period.start_date)
        for attempt in midterm_journal_sync.official_attempts(rows):
            with transaction.atomic():
                status, _row = midterm_journal_sync.sync_midterm_attempt(attempt, notify=False)
            self.counts[f"status_{status}"] += 1
            if status != NO_ENROLLMENT:
                continue
            if self._removed(attempt):
                self.counts["removed_skipped"] += 1
                self.by_exam[(attempt.exam_id, "removed_skipped")] += 1
                continue
            try:
                with transaction.atomic():
                    code, enrollment, receipt = self._place(organization, attempt, actor)
                    after = None
                    if enrollment is not None:
                        fresh = self._fresh(attempt)
                        after, _row = midterm_journal_sync.sync_midterm_attempt(fresh, notify=False)
            except IntegrityError:
                code, enrollment, receipt, after = "write_blocked_integrity", None, None, None
            self.counts[code] += 1
            self.by_exam[(attempt.exam_id, code)] += 1
            if after is not None:
                self.counts[f"after_{after}"] += 1
            if receipt is not None:
                receipts.append({**receipt, "exam": str(attempt.exam_id), "student": attempt.user_id})
        placement.receipt(organization=organization, actor=actor, batch=self.batch, placements=receipts)
        self.counts["receipts"] = len(receipts)

    def _removed(self, attempt) -> bool:
        if getattr(attempt, "supervision_status", "") == "removed":
            return True
        Ticket = django_apps.get_model("exams", "FinalExamTicket")
        return Ticket.objects.filter(attempt_id=attempt.pk, status="removed").exists()

    def _fresh(self, attempt):
        return (
            ExamAttempt.objects.select_related("exam", "exam__organization", "user")
            .prefetch_related("exam__journal_offerings")
            .get(pk=attempt.pk)
        )

    def _cotakers(self, attempt) -> list:
        """EYNİ imtahanı EYNİ oturumda verənlər (bilet oturumu; yoxdursa başlama vaxtı ±60 dəq.)."""
        Ticket = django_apps.get_model("exams", "FinalExamTicket")
        session_id = (
            Ticket.objects.filter(attempt_id=attempt.pk)
            .exclude(session__isnull=True)
            .values_list("session_id", flat=True)
        ).first()
        if session_id:
            ids = Ticket.objects.filter(exam_id=attempt.exam_id, session_id=session_id).values_list(
                "student_id", flat=True
            )
        else:
            started = attempt.started_at
            if started is None:
                return []
            ids = ExamAttempt.objects.filter(
                exam_id=attempt.exam_id,
                is_trial=False,
                started_at__gte=started - WINDOW,
                started_at__lte=started + WINDOW,
            ).values_list("user_id", flat=True)
        return [pk for pk in set(ids) if pk != attempt.user_id]

    def _place(self, organization, attempt, actor) -> tuple:
        """→ ``(kod, Enrollment | None, qəbz | None)``."""
        student_gaps = exam_journal_gaps.student_gaps
        exam = attempt.exam
        if exam.pk not in self.units:
            self.units[exam.pk] = list(exam.allowed_units.values_list("pk", flat=True))
        units = self.units[exam.pk]
        gap = student_gaps.classify_student(
            self.ctx, student_id=attempt.user_id, subject_id=exam.subject_id, exam_group_ids=units
        )
        self.counts[f"reason_{gap.reason}"] += 1
        if gap.reason == student_gaps.DROPPED:
            code, row = student_gaps.restore_dropped(
                self.ctx, student_id=attempt.user_id, subject_id=exam.subject_id, actor=actor
            )
            receipt = {"enrollment": str(row.pk), "event": "", "offering": str(row.offering_id)} if row else None
            return code, row, receipt
        target = gap.offering_id if gap.reason in student_gaps.PLACEABLE else None
        if gap.reason in (student_gaps.FAMILY_AMBIGUOUS, student_gaps.OTHER_GROUP_AMBIGUOUS):
            candidates = student_gaps.candidate_offering_ids(
                self.ctx, student_id=attempt.user_id, subject_id=exam.subject_id, exam_group_ids=units
            )
            target, how = student_gaps.cotaker_offering(
                self.ctx,
                subject_id=exam.subject_id,
                candidate_offering_ids=candidates,
                cotaker_ids=self._cotakers(attempt),
            )
            self.counts[how] += 1
            if target is None:
                return "skip_" + how, None, None
        if target is None:
            return f"skip_{gap.reason}", None, None
        code, row, receipt = placement.place(
            organization=organization, student=attempt.user, offering_ids=[target], actor=actor
        )
        return code, row, receipt

    def _report(self, apply) -> None:
        self.stdout.write(f"{PREFIX} mode {'apply' if apply else 'dry_run'}=1")
        body = " ".join(f"{key}={self.counts[key]}" for key in sorted(self.counts)) or "none=0"
        self.stdout.write(f"{PREFIX} totals {body}")
        self.stdout.write(f"{PREFIX} batch id={self.batch}")
        for (exam_id, code), count in sorted(self.by_exam.items()):
            self.stdout.write(f"{PREFIX} exam id={exam_id} code={code} n={count}")
