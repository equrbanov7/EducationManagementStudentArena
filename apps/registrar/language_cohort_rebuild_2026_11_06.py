"""Xarici dil SƏVİYYƏ qrupları — rəsmi siyahılar üzrə yenidən qurulma (sahib 2026-11-06).

Sahib: «level qrupları bu formadadır, bunları formalaşdır — hal-hazırda qarışıq düşübdü. Səliqəli və bu formada
olsun. Müəllimlər gedib hər leveldə tamam başqa uşaqları, hər uşaqda özünə aid olmayan levelləri görməsin.»

Rəsmi siyahı (Beginner / Elementary / Pre-Intermediate / Intermediate) hər SİNFİ bir müəllim + başlama saatı + otaq
+ tələbələr kimi verir. Əvvəl tələbə ev qrupunun bir neçə səviyyə jurnalında birdən idi, müəllim isə ev qrupunun
bütün səviyyə jurnalını (başqa siniflərin uşaqları ilə) görürdü. Plan — YALNIZ id-lər: :data:`PLAN_FILE`.

Hər sinif üçün (sinif başına atomik, idempotent — ``name`` = sinif kodu, məs. «E-38»):

* ``LanguageLevelCohort`` + öz qrupu + jurnalı (müəllim = sinfin müəllimi, saat = mənbə jurnalın plan saatı);
* hər tələbə: kohort jurnalına qeydiyyat; tələbənin ailə («… kommunikasiya-1») səviyyə qeydiyyatlarından YALNIZ
  SİNFİN MÜƏLLİMİNİN keçdiyi dərslər (tarix + başlama + növ üzrə birləşir) xanaları ilə köçürülür; köhnə səviyyə
  qeydiyyatları ``dropped`` olur (xanalar tarixçədə qalır), ``LanguageLevelPlacement`` («move») yazılır;
* yekun qiyməti / imtahan balı / bağlı jurnalı olan tələbəyə toxunulmur (sayılır — RİM ayrıca baxır);
* kohortun cədvəli: müəllimin mənbə jurnallarındakı sinfin başlama saatlı slotları (gün, saat, həftə, növ);
  siyahıda otaq varsa o yazılır;
* siyahıda olmayan «qalan» tələbələr — :mod:`.language_cohort_leftovers_2026_11_06` (başqa fəndə iştirakı varsa
  «Fəndən azad», yoxdursa dondurma);
* sonda AKTİV tələbəsi qalmayan köhnə səviyyə jurnalları deaktiv olunur (dərsləri və xanaları silinmir).

``undo`` — :func:`undo`: kohortlar deaktiv, köhnə qeydiyyatlar bərpa, deaktiv olunan jurnallar yenidən aktiv.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import uuid

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .language_levels import level_family, level_of
from .twin_merge import _LESSON_FIELDS
from .twin_relocate import copy_mark, recompute_absences

PLAN_FILE = pathlib.Path(__file__).with_name("language_cohorts_2026_11_06.json")
REASON = "Sahib 2026-11-06: xarici dil səviyyə qrupları rəsmi siyahı üzrə yenidən quruldu"
DEACTIVATED = "registrar.language_cohort_rebuild.deactivated"
DEFAULT_HOURS = {"seminar": 105}
_KINDS = ("lecture", "seminar", "lab")


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def load_plan(path=None) -> dict:
    return json.loads(pathlib.Path(path or PLAN_FILE).read_text(encoding="utf-8"))


class Rebuild:
    def __init__(self, *, organization, actor, counts, plan):
        self.organization, self.actor, self.counts, self.plan = organization, actor, counts, plan
        self.touched_sources: set = set()
        self._shared: dict = {}

    # ── giriş ─────────────────────────────────────────────────────────────
    def run(self) -> None:
        Period, OrgUnit = _model("AcademicPeriod", "organizations"), _model("OrgUnit", "organizations")
        self.period = Period.objects.filter(organization=self.organization, pk=self.plan["period"]).first()
        self.department = OrgUnit.objects.filter(organization=self.organization, pk=self.plan["department"]).first()
        if self.period is None or self.department is None:
            self.counts["plan_scope_missing"] += 1
            return
        for row in self.plan["classes"]:
            with transaction.atomic():
                self._class(row)
        from .language_cohort_leftovers_2026_11_06 import settle

        settle(self)
        with transaction.atomic():
            self._deactivate_empty_sources()

    # ── sinif ─────────────────────────────────────────────────────────────
    def _class(self, row) -> None:
        from django.contrib.auth import get_user_model

        teacher = get_user_model().objects.filter(pk=row.get("teacher") or 0, is_active=True).first()
        subject = _model("Subject").objects.filter(organization=self.organization, pk=row["subject"]).first()
        if teacher is None or subject is None or level_of(subject.name) != row["level"]:
            self.counts["classes_without_teacher_or_subject"] += 1
            return
        cohort, created = self._cohort(row, teacher, subject)
        self.counts["cohorts_created" if created else "cohorts_existing"] += 1
        lessons = self._lesson_index(cohort.offering)
        targets, sources_seen = [], []
        for student_id in row["students"]:
            target, sources = self._student(cohort, teacher, student_id, lessons)
            if target is not None:
                targets.append(target)
                sources_seen.extend(sources)
        recompute_absences(targets)
        self._slots(cohort, teacher, row, sources_seen)

    def _cohort(self, row, teacher, subject):
        Cohort, Offering = _model("LanguageLevelCohort"), _model("CourseOffering")
        found = (
            Cohort.objects.select_related("offering")
            .filter(organization=self.organization, department=self.department, period=self.period, name=row["code"])
            .first()
        )
        if found is not None:
            return found, False
        OrgUnit = _model("OrgUnit", "organizations")
        hours = self._hours(subject, row)
        level = level_of(subject.name)
        group = OrgUnit.objects.create(
            organization=self.organization,
            parent=self.department,
            unit_type="group",
            name=f"{row['code']} · {level}",
            slug=f"language-level-{uuid.uuid4().hex}",
            settings={"language_level_cohort": True, "rebuild": "2026-11-06"},
        )
        offering = Offering.objects.create(
            organization=self.organization,
            group=group,
            subject=subject,
            period=self.period,
            instructor=teacher,
            lesson_hours=sum(hours.values()),
        )
        from .language_cohort_assessment import configure

        configure(offering=offering, actor=self.actor)
        cohort = Cohort.objects.create(
            organization=self.organization,
            department=self.department,
            group=group,
            offering=offering,
            period=self.period,
            name=row["code"],
            family=level_family(subject.name),
            level=level,
            created_by=self.actor,
            **{f"{kind}_hours": hours.get(kind, 0) for kind in _KINDS},
        )
        log_action(
            AuditAction.CREATE,
            user=self.actor,
            organization=self.organization,
            obj=cohort,
            new_values={"offering_id": str(offering.pk), "level": level, "teacher": teacher.pk},
            reason=REASON,
        )
        return cohort, True

    def _hours(self, subject, row) -> dict:
        from .plan_hours import plan_hours_for_offering

        Enrollment = _model("Enrollment")
        source = (
            Enrollment.objects.filter(
                organization=self.organization,
                student_id__in=row["students"],
                offering__subject=subject,
                offering__period=self.period,
                offering__is_active=True,
            )
            .select_related("offering")
            .first()
        )
        hours = {k: int(v) for k, v in (plan_hours_for_offering(source.offering) if source else {}).items() if v}
        return {k: v for k, v in hours.items() if k in _KINDS} or dict(DEFAULT_HOURS)

    # ── tələbə ────────────────────────────────────────────────────────────
    def _student(self, cohort, teacher, student_id, lessons):
        Enrollment, Record = _model("Enrollment"), _model("StudentAcademicRecord")
        record = (
            Record.objects.filter(
                organization=self.organization, student_id=student_id, is_active=True, status="enrolled"
            )
            .select_related("group")
            .first()
        )
        if record is None:
            self.counts["students_without_active_record"] += 1
            return None, []
        target = Enrollment.objects.filter(offering=cohort.offering, student_id=student_id).first()
        if target is not None and target.status == "enrolled":
            self.counts["students_already_placed"] += 1
            return None, []
        sources = self._sources(cohort, student_id)
        blocked = self._blocked(sources)
        if blocked:
            self.counts[blocked] += 1
            return None, []
        if target is None:
            target = Enrollment.objects.create(
                organization=self.organization,
                offering=cohort.offering,
                student_id=student_id,
                kind=sources[0].kind if sources else "mandatory",
                source_group=record.group,
                added_by=self.actor,
                added_at=timezone.now(),
            )
        else:
            target.status = "enrolled"
            target.save(update_fields=["status", "updated_at"])
        for source in sources:
            self._copy_marks(source, target, teacher, lessons)
            source.status = "dropped"
            source.save(update_fields=["status", "updated_at"])
            self.touched_sources.add(source.offering_id)
        self._event(cohort, record, sources, target)
        self.counts["students_placed"] += 1
        self.counts["source_enrollments_dropped"] += len(sources)
        if not sources:
            self.counts["students_added_without_source"] += 1
        return target, sources

    def _sources(self, cohort, student_id) -> list:
        Enrollment = _model("Enrollment")
        rows = (
            Enrollment.objects.select_for_update(of=("self",))
            .filter(
                organization=self.organization,
                student_id=student_id,
                offering__period=self.period,
                offering__is_active=True,
                status="enrolled",
            )
            .exclude(offering=cohort.offering)
            .select_related("offering__subject")
            .order_by("pk")
        )
        return [
            row
            for row in rows
            if level_of(row.offering.subject.name) and level_family(row.offering.subject.name) == cohort.family
        ]

    def _blocked(self, sources) -> str:
        from .guest_merge import release_block_reason

        for source in sources:
            if release_block_reason(source):
                return "students_blocked_final_or_locked"
            for name in ("ComponentScore", "ExamScoreEntry"):
                if _model(name).objects.filter(enrollment=source).exists():
                    return "students_blocked_scores"
        return ""

    def _lesson_index(self, offering) -> dict:
        Lesson = _model("Lesson")
        return {(row.date, row.start_time, row.kind): row for row in Lesson.objects.filter(offering=offering)}

    def _teaches(self, teacher, offering_id, owner_id, instructor_id) -> bool:
        """Dərs/slot sinfin müəllimininmi: müəllimi odur, və ya müəllimsizdir və o, jurnalın sahibi / pay sahibidir.

        Köhnə sistemdən gələn dərslərdə müəllim yazılmayıb; bölünmüş jurnalda (pay) sinfin müəllimi həmin dərsləri
        keçib — sahibə aid saymaq onun xanalarını tarixçədə gizlədirdi (dry-run: 2 133 xana)."""
        if instructor_id:
            return instructor_id == teacher.pk
        if owner_id == teacher.pk:
            return True
        shared = self._shared.get(teacher.pk)
        if shared is None:
            shared = self._shared[teacher.pk] = set(
                _model("JournalShare")
                .objects.filter(teacher_id=teacher.pk, is_active=True)
                .values_list("offering_id", flat=True)
            )
        return offering_id in shared

    def _copy_marks(self, source, target, teacher, lessons) -> None:
        Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
        owner = source.offering.instructor_id
        marks = (
            LessonMark.objects.filter(enrollment=source)
            .select_related("lesson")
            .order_by("lesson__date", "lesson__start_time", "created_at")
        )
        for mark in marks:
            lesson = mark.lesson
            if not self._teaches(teacher, source.offering_id, owner, lesson.instructor_id):
                self.counts["marks_other_teacher_kept"] += 1
                continue
            key = (lesson.date, lesson.start_time, lesson.kind)
            twin = lessons.get(key)
            if twin is None:
                twin = Lesson.objects.create(
                    organization=self.organization,
                    offering=target.offering,
                    **{name: getattr(lesson, name) for name in _LESSON_FIELDS},
                )
                Lesson.objects.filter(pk=twin.pk).update(created_at=lesson.created_at)
                lessons[key] = twin
                self.counts["lessons_created"] += 1
            if LessonMark.objects.filter(lesson=twin, enrollment=target).exists():
                self.counts["marks_duplicate_kept_first"] += 1
                continue
            copy_mark(mark, lesson=twin, enrollment=target)
            self.counts["marks_copied"] += 1

    def _event(self, cohort, record, sources, target) -> None:
        Placement = _model("LanguageLevelPlacement")
        for source in sources or [None]:
            Placement.objects.create(
                organization=self.organization,
                cohort=cohort,
                student_id=record.student_id,
                home_group=record.group,
                actor=self.actor,
                action="move" if source else "add",
                source_enrollment=source,
                target_enrollment=target,
                reason=REASON,
            )

    # ── cədvəl ────────────────────────────────────────────────────────────
    def _slots(self, cohort, teacher, row, sources) -> None:
        Slot = _model("ScheduleSlot")
        starts = {dt.time.fromisoformat(value) for value in row.get("start") or []}
        existing = {
            (slot.weekday, slot.start_time, slot.week_type, slot.kind)
            for slot in Slot.objects.filter(offering=cohort.offering)
        }
        candidates = [
            slot
            for slot in Slot.objects.filter(offering_id__in={source.offering_id for source in sources}, is_parked=False)
            .select_related("offering")
            .order_by("weekday", "start_time")
            if self._teaches(teacher, slot.offering_id, slot.offering.instructor_id, slot.instructor_id)
        ]
        at_start = [slot for slot in candidates if not starts or slot.start_time in starts]
        if at_start:
            plan = [(s.weekday, s.start_time, s.end_time, s.week_type, s.kind, s.room) for s in at_start]
        elif candidates and starts:
            # Müəllimin slotları başqa saatdadır — günlər qalır, saat rəsmi siyahıdandır (cüt dərs = 90 dəq).
            start = min(starts)
            end = (dt.datetime.combine(dt.date(2000, 1, 1), start) + dt.timedelta(minutes=90)).time()
            plan = sorted({(s.weekday, start, end, s.week_type, s.kind, s.room) for s in candidates})
            self.counts["cohorts_slots_moved_to_list_time"] += 1
        else:
            plan = []
        for weekday, start, end, week_type, kind, room in plan:
            key = (weekday, start, week_type, kind)
            if key in existing:
                continue
            Slot.objects.create(
                organization=self.organization,
                offering=cohort.offering,
                weekday=weekday,
                start_time=start,
                end_time=end,
                week_type=week_type,
                kind=kind,
                room=row.get("room") or room,
                created_by=self.actor,
            )
            existing.add(key)
            self.counts["slots_created"] += 1
        if not existing:
            self.counts["cohorts_without_slots"] += 1

    # ── köhnə jurnallar ──────────────────────────────────────────────────
    def _deactivate_empty_sources(self) -> None:
        Offering, Enrollment = _model("CourseOffering"), _model("Enrollment")
        for offering in Offering.objects.filter(pk__in=self.touched_sources, is_active=True).order_by("pk"):
            if Enrollment.objects.filter(offering=offering, status="enrolled").exists():
                self.counts["sources_kept_with_students"] += 1
                continue
            Offering.objects.filter(pk=offering.pk).update(is_active=False, updated_at=timezone.now())
            log_action(
                AuditAction.UPDATE,
                user=self.actor,
                organization=self.organization,
                obj=offering,
                old_values={"is_active": True},
                new_values={"is_active": False},
                reason=REASON,
                resource_type=DEACTIVATED,
                resource_id=str(offering.pk),
            )
            self.counts["sources_deactivated"] += 1


def run(*, organization, actor, counts, plan=None) -> None:
    Rebuild(organization=organization, actor=actor, counts=counts, plan=plan or load_plan()).run()


@transaction.atomic
def undo(*, organization, actor, counts, plan=None) -> None:
    """Geri qaytarma: kohortun aktiv qeydiyyatları → ``dropped``, köhnələri → ``enrolled``, jurnallar bərpa."""
    plan = plan or load_plan()
    Cohort, Placement = _model("LanguageLevelCohort"), _model("LanguageLevelPlacement")
    Enrollment, Offering = _model("Enrollment"), _model("CourseOffering")
    AuditLog = _model("AuditLog", "audit")
    names = [row["code"] for row in plan["classes"]]
    cohorts = list(
        Cohort.objects.filter(
            organization=organization, period_id=plan["period"], department_id=plan["department"], name__in=names
        ).select_related("offering", "group")
    )
    deactivated = list(
        AuditLog.objects.filter(organization=organization, resource_type=DEACTIVATED, reason=REASON).values_list(
            "resource_id", flat=True
        )
    )
    restored = Offering.objects.filter(organization=organization, pk__in=deactivated, is_active=False)
    counts["undo_sources_reactivated"] += restored.update(is_active=True, updated_at=timezone.now())
    for cohort in cohorts:
        moves = Placement.objects.filter(cohort=cohort, reason=REASON, source_enrollment__isnull=False)
        for event in moves.select_related("source_enrollment"):
            source = event.source_enrollment
            if source.status == "dropped":
                source.status = "enrolled"
                source.save(update_fields=["status", "updated_at"])
                counts["undo_sources_reenrolled"] += 1
        counts["undo_targets_dropped"] += Enrollment.objects.filter(offering=cohort.offering, status="enrolled").update(
            status="dropped", updated_at=timezone.now()
        )
        if cohort.offering.is_active:
            Offering.objects.filter(pk=cohort.offering_id).update(is_active=False, updated_at=timezone.now())
            counts["undo_cohorts_deactivated"] += 1
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=cohort,
            new_values={"undo": True},
            reason=f"{REASON} — geri qaytarıldı",
        )
