"""Qiymətləndirilmiş imtahan nəticəsi tələbənin öz səhifəsində / jurnalında varmı — audit + bərpa (sahib 2026-11-16).

Sahib: «qiymətləndirilmiş nəticəsi olan hər tələbə üçün nəticə öz səhifəsində görünsün, yeni jurnallarında
olub-olmadığını yoxla» və «imtahan verib o fəndən jurnalı yoxdursa — başqa qrupdadırsa o fəndə alt qrupdadır».

Hər RƏSMİ cəhd (bitmiş, sınaq olmayan, hər jurnal qeydiyyatı üzrə ən son; midterm və final) canlı körpü ilə EYNİ
yoldan keçirilir (``sync_midterm_scores`` / ``sync_final_scores``-in birləşmiş forması) və nəticə sayılır:

* ``unchanged`` — bal jurnaldadır (tələbə görür); ``written`` — jurnalda YOX idi / fərqli idi → yazılır;
* ``no_enrollment`` — tələbə fənnin heç bir jurnalında deyil → SƏBƏB sayılır (``registrar.exam_result_gaps``). Bu əmr
  tələbəni jurnala YAZMIR — yerləşdirmə mövcud rəsmi addımdır: ``merge_duplicate_subjects_20261111 --only takers``
  (sahib 2026-11-11, alt qrup tələbəsi kimi sənədsiz; paket + geri qaytarma), sonra bu əmr yenidən;
* qalan statuslar (bağlı jurnal, sənədli düzəliş, gizli nəticə, yoxlanmamış, …) olduğu kimi sayılır.

Görünmə yoxlaması: yazılmış / dəyişməz balın qeydiyyatı ``dropped`` deyil (tələbə kartı görür); eyni fəndən ikinci
aktiv kart (boş qala bilər) sayılır. Kağız (İmtahan Mərkəzi) nəticəsi ``dropped`` qeydiyyatdadırsa sayılır.

Təhlükəsizlik: DEFOLT DRY-RUN (eyni kod tranzaksiyada işləyir, sonda geri qaytarılır — saylar dəqiqdir); yalnız
qeydiyyat yaradılmır / silinmir; idempotent; bildiriş GETMİR; stdout-a YALNIZ saylar + imtahan id / fənn kodu.

    manage.py audit_exam_results_20261116 --org qku --actor <superadmin>                  # DRY-RUN
    manage.py audit_exam_results_20261116 --org qku --actor <superadmin> --apply
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.exams.models import Exam, ExamAttempt
from apps.exams.services import exam_journal_link, journal_sync, midterm_journal_sync
from apps.exams.services.access_policy import FINAL_EXAM_CATEGORY
from apps.exams.services.journal_sync import official_final_attempts
from apps.organizations.models import Organization
from apps.registrar.public import exam_journal_gaps
from apps.registrar.public import exam_journal_link as registrar_link
from core.rls import bypass_rls
from core.rls_pooling import rls_worker_atomic

PREFIX = "exam_results:"
NO_ENROLLMENT = "no_enrollment"
_REWRITE = frozenset({"written", "unchanged"})


class _DryRun(Exception):
    """Dry-run tranzaksiyasını geri qaytarmaq üçün."""


def _line(stdout, label, counts) -> None:
    body = " ".join(f"{key}={counts[key]}" for key in sorted(counts)) or "none=0"
    stdout.write(f"{PREFIX} {label} {body}")


class Command(BaseCommand):
    help = "Qiymətləndirilmiş imtahan nəticələri jurnalda / tələbə səhifəsində varmı: audit + bərpa (defolt dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--org", required=True, help="təşkilatın slug-ı (məs. qku)")
        parser.add_argument("--actor", required=True, help="aktiv superadmin istifadəçi adı (audit müəllifi)")
        parser.add_argument("--apply", action="store_true", help="həqiqətən yaz (defolt: dry-run)")
        parser.add_argument("--detail", action="store_true", help="jurnalsız hallar: fənn kodu + qrup adı (şəxssiz)")

    def handle(self, *args, **options):
        apply = bool(options["apply"])
        self.counts = {"midterm": Counter(), "final": Counter()}
        self.gaps = {"midterm": Counter(), "final": Counter()}
        self.visibility: Counter = Counter()
        self.paper: Counter = Counter()
        self.cleanup: Counter = Counter()
        self.gap_rows: Counter = Counter()
        self.details: Counter = Counter()
        self.detail = bool(options.get("detail"))
        self.relinked = 0
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
                try:
                    with transaction.atomic():
                        self._run(organization, period)
                        if not apply:
                            raise _DryRun
                except _DryRun:
                    pass
        except CommandError:
            raise
        except Exception as exc:  # prod-data-ops traceback-i gizlədir — kod görünsün
            raise CommandError(f"audit_failed_{type(exc).__name__.lower()}") from exc
        self._report(apply)

    # ── addımlar ────────────────────────────────────────────────────────────────
    def _run(self, organization, period) -> None:
        exams = list(
            Exam.objects.filter(
                organization=organization,
                is_deleted=False,
                subject__isnull=False,
                exam_type_extended__in=[journal_sync.MIDTERM_EXAM_CATEGORY, FINAL_EXAM_CATEGORY],
            )
            .select_related("organization", "journal_teacher")
            .order_by("pk")
        )
        for exam in exams:
            old_ids, new_ids = exam_journal_link.refresh_links(exam)
            self.relinked += int(old_ids != new_ids)
        attempts = ExamAttempt.objects.filter(exam__organization=organization)
        self.before_finals = self._final_scores(organization)
        pending = []
        for attempt in midterm_journal_sync.official_attempts(attempts):
            status, row = self._sync("midterm", attempt)
            self._count("midterm", attempt, status, row, pending)
        for attempt in official_final_attempts(attempts):
            status, row = self._sync("final", attempt)
            self._count("final", attempt, status, row, pending)
        for exam in exams:
            self.cleanup.update(exam_journal_link.clear_stale(exam))
        self._gaps(organization, period, pending)
        self._paper(organization, period)

    def _sync(self, kind, attempt):
        with transaction.atomic():
            if kind == "midterm":
                return midterm_journal_sync.sync_midterm_attempt(attempt, notify=False)
            status, row = journal_sync.sync_final_attempt(attempt)
        if status == "written" and row is not None and hasattr(row, "exam_score"):
            if self.before_finals.get(row.enrollment_id, object()) == row.exam_score:
                status = "unchanged"
        return status, row

    def _final_scores(self, organization) -> dict:
        FinalGrade = django_apps.get_model("registrar", "FinalGrade")
        return dict(
            FinalGrade.objects.filter(organization=organization, exam_score__isnull=False).values_list(
                "enrollment_id", "exam_score"
            )
        )

    def _count(self, kind, attempt, status, row, pending) -> None:
        self.counts[kind][status] += 1
        if status == NO_ENROLLMENT:
            pending.append((kind, attempt))
        elif status in _REWRITE and row is not None:
            self._visible(kind, row)

    def _visible(self, kind, row) -> None:
        enrollment = getattr(row, "enrollment", None)
        if enrollment is None:
            return
        Enrollment = django_apps.get_model("registrar", "Enrollment")
        if enrollment.status == Enrollment.Status.DROPPED:
            self.visibility[f"{kind}_on_dropped"] += 1
            return
        self.visibility[f"{kind}_visible"] += 1
        offering = enrollment.offering
        twin_cards = (
            Enrollment.objects.filter(
                student_id=enrollment.student_id,
                offering__period_id=offering.period_id,
                offering__subject_id=offering.subject_id,
            )
            .exclude(pk=enrollment.pk)
            .exclude(status=Enrollment.Status.DROPPED)
        )
        if twin_cards.exists():
            self.visibility[f"{kind}_second_card"] += 1

    def _gaps(self, organization, period, pending) -> None:
        if not pending:
            return
        student_gaps = exam_journal_gaps.student_gaps
        ctx = student_gaps.context(organization, period)
        units: dict = {}
        for kind, attempt in pending:
            exam = attempt.exam
            if exam.pk not in units:
                units[exam.pk] = list(exam.allowed_units.values_list("pk", flat=True))
            gap = student_gaps.classify_student(
                ctx, student_id=attempt.user_id, subject_id=exam.subject_id, exam_group_ids=units[exam.pk]
            )
            self.gaps[kind][gap.reason] += 1
            self.gap_rows[(kind, exam.pk, gap.reason)] += 1
            if self.detail:
                code, group, hint = student_gaps.describe(
                    ctx, gap, student_id=attempt.user_id, subject_id=exam.subject_id, exam_group_ids=units[exam.pk]
                )
                self.details[(exam.pk, gap.reason, code, group, hint)] += 1

    def _paper(self, organization, period) -> None:
        """İmtahan Mərkəzinin kağız nəticəsi tələbənin GÖRMƏDİYİ (``dropped``) qeydiyyatdadırmı."""
        Entry = django_apps.get_model("registrar", "ExamScoreEntry")
        Enrollment = django_apps.get_model("registrar", "Enrollment")
        rows = (
            Entry.objects.filter(organization=organization, enrollment__offering__period=period)
            .values_list("enrollment_id", "assessment", "enrollment__status", "enrollment__student_id")
            .distinct()
        )
        seen = set()
        for enrollment_id, assessment, status, student_id in rows:
            if (enrollment_id, assessment) in seen:
                continue
            seen.add((enrollment_id, assessment))
            self.paper[f"{assessment}_entries"] += 1
            if status != Enrollment.Status.DROPPED:
                continue
            self.paper[f"{assessment}_on_dropped"] += 1
            moved = Enrollment.objects.filter(
                student_id=student_id,
                offering__period=period,
                offering__subject_id=Enrollment.objects.filter(pk=enrollment_id).values("offering__subject_id")[:1],
            ).exclude(status=Enrollment.Status.DROPPED)
            if moved.exists():
                self.paper[f"{assessment}_on_dropped_other_card"] += 1

    def _report(self, apply) -> None:
        self.stdout.write(f"{PREFIX} mode {'apply' if apply else 'dry_run'}=1")
        for kind in ("midterm", "final"):
            _line(self.stdout, f"{kind}_status", self.counts[kind])
            _line(self.stdout, f"{kind}_no_enrollment_reason", self.gaps[kind])
        _line(self.stdout, "visibility", self.visibility)
        _line(self.stdout, "paper", self.paper)
        _line(self.stdout, "stale_cells", self.cleanup)
        self.stdout.write(f"{PREFIX} links relinked={self.relinked}")
        for (kind, exam_id, reason), count in sorted(self.gap_rows.items(), key=lambda item: (-item[1], item[0])):
            self.stdout.write(f"{PREFIX} gap kind={kind} exam={exam_id} reason={reason} n={count}")
        for (exam_id, reason, code, group, hint), count in sorted(self.details.items(), key=lambda item: item[0]):
            line = f"{PREFIX} detail exam={exam_id} reason={reason} subject={code} group={group} n={count} | {hint}"
            self.stdout.write(line[:400])
