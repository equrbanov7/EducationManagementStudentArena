"""Köhnə sistem jurnallarında ikiqat saat — toplu düzəliş + undo (sahib 2026-11-17, MR-000482).

Köhnə sistem bəzi semestrlərdə (əsasən 2023/2024 Yaz) hər akademik saatı ayrıca sətir kimi saxlayırdı, köçürmə isə
hər sətri 2 saatlıq dərs yazdı — «keçirilən saat» və qayıb saatı ikiqat oldu. Qayda: :mod:`.legacy_hour_rows_rule`.

Əhatə: CARİ semestrdən ƏVVƏLKİ semestrlərin aktiv jurnalları; yalnız köçürmə dərsləri (``created_by`` boş, passiv
deyil). Rəsmi düzəlişli dərs (``LessonCorrection``) toxunulmur və sayılır. Hədəf sətir:

* xanası VAR — ``hours`` 2 → 1 (xanalar dəyişmir);
* HEÇ BİR xanası yoxdur — boş artıq sətir silinir (audit-də tam snapshot).

Sonra jurnalın bütün qeydiyyatlarının qayıb saatı yenidən hesablanır (``recompute_absence_hours_many``). Yekun nəticəyə
(``FinalGrade``, imtahan körpüsü, ``legacy_qb_fail``) toxunulmur. Buraxılış statusu dəyişən qeydiyyatlar
:func:`apps.registrar.exam_eligibility.resolve` ilə sayılır (donmuş jurnalda status onsuz da hesablanmır).

Hər jurnalın «Dəyişiklik tarixçəsi»nə bir sətir + bir ``AuditLog`` (``resource_type`` = :data:`CHANGED`, paket id-si
``batch``, endirilən dərs id-ləri, silinən dərslərin snapshot-u). ``undo`` həmin izlə: saatı HƏLƏ 1 olan dərslər 2-yə
qaytarılır, silinən dərslər eyni id ilə bərpa olunur, qayıb saatı yenidən hesablanır.
"""

from __future__ import annotations

import datetime
import secrets

from django.apps import apps as django_apps
from django.db.models import Count, Sum
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from . import absence_limit, exam_eligibility, grade_audit
from .legacy_hour_rows_rule import HOUR_MODE, NEW_HOURS, NO_CHANGE, OLD_HOURS, Row, decide
from .mexanika_lessons_fix_2026_11_08 import _fields, _snapshot
from .twin_relocate import corrected_lesson_ids, recompute_absences

SOURCE = "legacy_hour_rows_20261117"
CHANGED = "registrar.legacy_hour_rows_2026_11_17.changed"
REASON = "Sahib 2026-11-17: köhnə sistemin saat-saat yazdığı dərslər 1 akademik saata endirildi (MR-000482)"
UNDO_REASON = "Sahib 2026-11-17: köhnə sistem dərslərinin saat düzəlişi geri qaytarıldı"
BATCH_PREFIX = "lghours-"


def new_batch_id() -> str:
    return f"{BATCH_PREFIX}{timezone.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def past_periods(organization) -> list:
    """Cari semestrdən (``is_current``) ƏVVƏL başlayıb ondan əvvəl BİTƏN semestrlər; cari semestr yoxdursa boş."""
    Period = _model("AcademicPeriod", "organizations")
    current = (
        Period.objects.filter(organization=organization, is_current=True)
        .exclude(start_date=None)
        .order_by("-start_date")
    ).first()
    if current is None:
        return []
    return list(
        Period.objects.filter(
            organization=organization, start_date__lt=current.start_date, end_date__lt=current.start_date
        ).order_by("start_date")
    )


def period_key(period) -> str:
    return f"{period.start_date:%Y-%m-%d}"


#: ``registrar_member_has_permission(org, user, 'grade.input')`` (DB funksiyası) ilə eyni icazə dəsti.
GRADE_INPUT_PERMISSIONS = frozenset({"grade.input", "grading.input", "grade.*", "grading.*", "*"})


def grade_input_users(organization, user_ids) -> set:
    """DB qoruyucusu ``registrar_active_member_instructor_guard``-ın Python güzgüsü (tək sorğu): müəllim sahəsinə
    yenidən yazıla bilən istifadəçilər. DB funksiyasının özü tətbiq roluna açıq deyil (``REVOKE … FROM PUBLIC``)."""
    wanted = sorted({pk for pk in user_ids if pk is not None})
    if not wanted:
        return set()
    rows = (
        _model("Membership", "organizations")
        .objects.filter(
            organization=organization,
            user_id__in=wanted,
            is_active=True,
            role__is_active=True,
            role__organization=organization,
            user__is_active=True,
            organization__is_active=True,
        )
        .values_list("user_id", "role__permissions")
    )
    return {user_id for user_id, permissions in rows if GRADE_INPUT_PERMISSIONS & set(permissions or ())}


class _Status:
    """Jurnalın qeydiyyatları: yenidən hesablama hamısına, buraxılış SAYI isə aktivlərə (:func:`exam_eligibility.resolve`)."""

    def __init__(self, offering):
        Enrollment = _model("Enrollment")
        self.offering = offering
        self.all_enrollments = list(
            Enrollment.objects.filter(offering=offering).only(
                "id", "student_id", "organization_id", "offering_id", "absence_hours", "status", "superseded_by_id"
            )
        )
        self.enrollments = [
            row for row in self.all_enrollments if row.superseded_by_id is None and row.status != "dropped"
        ]
        self.frozen = offering.pk in exam_eligibility.frozen_offering_ids([offering.pk])
        self.exempt = exam_eligibility.exempt_student_ids(
            offering.organization, [row.student_id for row in self.enrollments]
        )
        self.before_absence: dict = {}

    def _denominator(self) -> int:
        if self.offering.lesson_hours:
            return int(self.offering.lesson_hours)
        held = _model("Lesson").objects.filter(offering=self.offering, is_passive=False).aggregate(total=Sum("hours"))
        return int(held["total"] or 0)

    def snapshot(self, absence: dict) -> dict:
        if not self.enrollments:
            return {}
        total = self._denominator()
        limits = absence_limit.row_limits(
            organization_id=self.offering.organization_id, enrollments=self.enrollments, total_hours=total
        )
        result = {}
        for enrollment in self.enrollments:
            limit = limits.get(enrollment.student_id)
            result[enrollment.pk] = exam_eligibility.resolve(
                absence_hours=absence.get(enrollment.pk, 0),
                lesson_hours=total,
                limit_percent=limit.percent if limit else exam_eligibility.DEFAULT_LIMIT_PERCENT,
                exempt=enrollment.student_id in self.exempt,
                frozen=self.frozen,
            )["barred"]
        return result

    def absences(self) -> dict:
        ids = [enrollment.pk for enrollment in self.enrollments]
        return dict(_model("Enrollment").objects.filter(pk__in=ids).values_list("pk", "absence_hours"))


def _history(offering, actor, *, hours=(0, "", ""), deleted=(0, "", "")) -> None:
    """«Dəyişiklik tarixçəsi»nə bir sətir: ``hours``/``deleted`` = ``(say, köhnə, yeni)``."""
    changes = []
    if hours[0]:
        changes.append(
            {"student": "—", "item": f"Köhnə sistem dərsləri ({hours[0]} sətir)", "old": hours[1], "new": hours[2]}
        )
    if deleted[0]:
        changes.append(
            {"student": "—", "item": f"Boş artıq sətirlər ({deleted[0]})", "old": deleted[1], "new": deleted[2]}
        )
    grade_audit.log_grade_changes(offering=offering, by_user=actor, kind="mark", changes=changes, reason=SOURCE)


class Runner:
    def __init__(self, *, organization, actor, counts, batch, period_counts):
        self.organization = organization
        self.actor = actor
        self.counts = counts
        self.batch = batch
        self.period_counts = period_counts
        self.students_unbarred: set = set()

    def run(self) -> None:
        periods = past_periods(self.organization)
        if not periods:
            self.counts["no_current_period"] += 1
            return
        Offering = _model("CourseOffering")
        offerings = (
            Offering.objects.filter(organization=self.organization, period__in=periods)
            .select_related("period", "organization", "subject")
            .order_by("period__start_date", "pk")
        )
        for offering in offerings.iterator(chunk_size=200):
            self._offering(offering)
        self.counts["students_unbarred"] = len(self.students_unbarred)

    def _bump(self, offering, key, value=1) -> None:
        self.counts[key] += value
        self.period_counts.setdefault(period_key(offering.period), {}).setdefault(key, 0)
        self.period_counts[period_key(offering.period)][key] += value

    def _offering(self, offering) -> None:
        Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
        legacy = list(
            Lesson.objects.filter(offering=offering, created_by__isnull=True, is_passive=False).values_list(
                "id", "date", "start_time", "hours", "instructor_id"
            )
        )
        if not legacy:
            return
        rows = [Row(*values[:4]) for values in legacy]
        full = decide(rows, offering.lesson_hours)
        if full.mode == NO_CHANGE:
            return
        if not offering.is_active:
            self._bump(offering, "inactive_offerings_skipped")
            return
        marked = set(
            LessonMark.objects.filter(lesson_id__in=[row.id for row in rows])
            .values("lesson_id")
            .annotate(n=Count("id"))
            .values_list("lesson_id", flat=True)
        )
        filled = [row for row in rows if row.id in marked]
        # Endirmə qərarı YALNIZ xanalı sətirlər üzrə verilir: cütün boş təkrarı silinəndə qalan sətir yarıya enməsin.
        # Saat rejimli jurnalda (bütöv saat-saat yazılıb) xanalı 2 saatlıq bütün sətirlər endirilir.
        if full.mode == HOUR_MODE:
            lower = {row.id for row in filled if row.hours == OLD_HOURS}
        else:
            lower = decide(filled, offering.lesson_hours).targets
        empty = [pk for pk in full.targets if pk not in marked]
        corrected = corrected_lesson_ids(list(lower) + empty)
        self._bump(offering, "corrected_lessons_skipped", sum(1 for pk in list(lower) + empty if str(pk) in corrected))
        lower = [pk for pk in lower if str(pk) not in corrected]
        empty = [pk for pk in empty if str(pk) not in corrected]
        # Boş sətrin müəllimi BAŞQA biridir və artıq aktiv üzv deyilsə sətir silinmir (undo onu həmin müəllimlə bərpa
        # edə bilməz, DB qoruyucusu) — 1 saata enir. Jurnalın öz müəllimidirsə undo sahəni boş bərpa edir (boş = jurnalın
        # müəllimi, görünüş eynidir), ona görə silinir.
        instructors = {values[0]: values[4] for values in legacy}
        foreign = {instructors[pk] for pk in empty if instructors[pk] not in (None, offering.instructor_id)}
        allowed = grade_input_users(self.organization, foreign)
        stuck = [pk for pk in empty if instructors[pk] in foreign and instructors[pk] not in allowed]
        if stuck:
            self._bump(offering, "empty_kept_inactive_instructor", len(stuck))
            lower += stuck
            empty = [pk for pk in empty if pk not in set(stuck)]
        if not (lower or empty):
            return
        status = _Status(offering)
        status.before_absence = status.absences()
        before = status.snapshot(status.before_absence)
        lowered_ids = list(Lesson.objects.filter(pk__in=lower, hours=OLD_HOURS).values_list("pk", flat=True))
        Lesson.objects.filter(pk__in=lowered_ids).update(hours=NEW_HOURS)
        snapshots = [
            _snapshot(lesson)
            for lesson in Lesson.objects.select_for_update(of=("self",)).filter(pk__in=empty, marks__isnull=True)
        ]
        Lesson.objects.filter(pk__in=[item["id"] for item in snapshots], marks__isnull=True).delete()
        recompute_absences(status.all_enrollments)
        after = status.snapshot(status.absences())
        deleted_ids = {item["id"] for item in snapshots}
        lowered_set = set(lowered_ids)
        held_after = sum(
            NEW_HOURS if row.id in lowered_set else int(row.hours or 0)
            for row in rows
            if str(row.id) not in deleted_ids
        )
        self._tally(offering, full, status, before, after, lowered=len(lowered_ids), deleted=len(snapshots))
        self._plan_fit(offering, full.total_before, held_after)
        _history(
            offering,
            self.actor,
            hours=(len(lowered_ids), "2 saat", "1 saat"),
            deleted=(len(snapshots), "var", "silindi"),
        )
        log_action(
            AuditAction.UPDATE,
            user=self.actor,
            organization=self.organization,
            old_values={"hours": {str(pk): OLD_HOURS for pk in lowered_ids}},
            new_values={
                "batch": self.batch,
                "period_id": str(offering.period_id),
                "mode": full.mode,
                "lessons": [str(pk) for pk in lowered_ids],
                "deleted": snapshots,
            },
            reason=REASON,
            resource_type=CHANGED,
            resource_id=str(offering.pk),
            resource_repr="Köhnə sistem dərsləri: 2 saat → 1 saat",
        )

    def _plan_fit(self, offering, before, after) -> None:
        plan = int(offering.lesson_hours or 0)
        if not plan:
            self._bump(offering, "offerings_no_plan")
            return
        self._bump(offering, "plan_fit_before", int(abs(before - plan) <= plan * 0.15))
        self._bump(offering, "plan_fit_after", int(abs(after - plan) <= plan * 0.15))
        self._bump(offering, "under_plan_before", int(before < plan * 0.85))
        self._bump(offering, "under_plan_after", int(after < plan * 0.85))

    def _tally(self, offering, decision, status, before, after, *, lowered, deleted) -> None:
        self._bump(offering, "offerings")
        self._bump(offering, "offerings_hour_mode" if decision.mode == HOUR_MODE else "offerings_window_mode")
        self._bump(offering, "offerings_frozen", int(status.frozen))
        self._bump(offering, "lessons_one_hour", lowered)
        self._bump(offering, "lessons_empty_deleted", deleted)
        self._bump(offering, "tiny_gap_rows", decision.tiny_gap_rows)
        self._bump(offering, "enrollments", len(status.enrollments))
        absence_before, absence_after = status.before_absence, status.absences()
        self._bump(
            offering,
            "enrollments_absence_changed",
            sum(1 for pk, h in absence_after.items() if absence_before.get(pk) != h),
        )
        unbarred = [pk for pk, barred in before.items() if barred and not after.get(pk)]
        self._bump(offering, "enrollments_barred_before", sum(1 for value in before.values() if value))
        self._bump(offering, "enrollments_barred_after", sum(1 for value in after.values() if value))
        self._bump(offering, "enrollments_unbarred", len(unbarred))
        self._bump(
            offering, "enrollments_newly_barred", sum(1 for pk, value in after.items() if value and not before.get(pk))
        )
        if unbarred:
            finals = set(
                _model("FinalGrade").objects.filter(enrollment_id__in=unbarred).values_list("enrollment_id", flat=True)
            )
            self._bump(offering, "unbarred_with_final_grade", len(finals))
            by_id = {enrollment.pk: enrollment for enrollment in status.enrollments}
            self.students_unbarred.update(by_id[pk].student_id for pk in unbarred)


def run(*, organization, actor, counts, batch, period_counts) -> None:
    Runner(organization=organization, actor=actor, counts=counts, batch=batch, period_counts=period_counts).run()


def undo(*, organization, actor, counts, batch) -> None:
    """Paketin audit izinə görə: saatı HƏLƏ 1 olan dərslər 2-yə, silinənlər eyni id ilə bərpa olunur."""
    Offering, Lesson, Enrollment = _model("CourseOffering"), _model("Lesson"), _model("Enrollment")
    AuditLog = _model("AuditLog", "audit")
    entries = AuditLog.objects.filter(organization=organization, resource_type=CHANGED, new_values__batch=batch)
    for entry in entries.order_by("created_at", "pk"):
        counts["undo_entries"] += 1
        offering = Offering.objects.filter(organization=organization, pk=entry.resource_id).first()
        values = entry.new_values or {}
        if offering is None:
            counts["undo_offering_missing"] += 1
            continue
        ids = [pk for pk in values.get("lessons") or [] if isinstance(pk, str)]
        restored = Lesson.objects.filter(offering=offering, pk__in=ids, hours=NEW_HOURS).update(hours=OLD_HOURS)
        counts["undo_hours_restored"] += restored
        counts["undo_hours_changed"] += len(ids) - restored
        recreated = 0
        for snapshot in values.get("deleted") or []:
            if Lesson.objects.filter(pk=snapshot["id"]).exists():
                counts["undo_lesson_exists"] += 1
                continue
            fields = _fields(snapshot)
            instructor = fields.get("instructor_id")
            if instructor is not None and instructor not in grade_input_users(organization, [instructor]):
                # DB qoruyucusu deaktiv müəllimi qəbul etmir — sahə boş (= jurnalın müəllimi); id audit snapshot-dadır.
                same = instructor == offering.instructor_id
                counts["undo_instructor_is_journal_teacher" if same else "undo_instructor_dropped"] += 1
                fields["instructor_id"] = None
            lesson = Lesson.objects.create(id=snapshot["id"], organization=organization, offering=offering, **fields)
            Lesson.objects.filter(pk=lesson.pk).update(
                created_at=datetime.datetime.fromisoformat(snapshot["created_at"])
            )
            recreated += 1
        counts["undo_lessons_recreated"] += recreated
        recompute_absences(list(Enrollment.objects.filter(offering=offering)))
        if not (restored or recreated):
            continue
        _history(
            offering, actor, hours=(restored, "1 saat", "2 saat"), deleted=(recreated, "silinmişdi", "bərpa olundu")
        )
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            old_values={"hours": {pk: NEW_HOURS for pk in ids}},
            new_values={"undo_of": str(entry.pk), "batch": batch, "restored": restored, "recreated": recreated},
            reason=UNDO_REASON,
            resource_type=f"{CHANGED}.undo",
            resource_id=str(offering.pk),
        )


__all__ = ["BATCH_PREFIX", "CHANGED", "SOURCE", "new_batch_id", "past_periods", "period_key", "run", "undo"]
