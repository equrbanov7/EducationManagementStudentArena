"""Jurnalların boş xanaları — YALNIZ sistemdaxili mötəbər mənbədən (sahib 2026-11-10) — ``fill_empty_cells_20261110``.

Sahib: «jurnallarda çoxlu boş xana var — səbəbini araşdır, düzgün yolla doldur». Hesabat:
``docs/audits/2026-11-10-empty-cells/REPORT.md``. Qiymət / davamiyyət UYDURULMUR — bu modul iki dəqiq halı düzəldir:

``dedupe`` — **eyni fəndən iki aktiv qeydiyyat, biri tam boşdur.** Dərs yükü axını (``_confirm_and_enroll``, düzəldi:
:mod:`apps.workload.services.enroll_guard`) tələbəni fənni artıq başqa jurnalda (legacy «alt qrupdan əlavə») keçdiyi
halda öz qrup jurnalına da yazırdı → öz qrup jurnalında keçmiş bütün dərslər «—». Həll 2026-10-24 ``dedupe`` fazası ilə
eynidir: ÖZ qrup qeydiyyatı (``source_group`` boş), onda HEÇ BİR xana / komponent / imtahan balı yoxdur, qarşısında
xanası olan dəqiq bir «alt qrupdan əlavə» sətri var → :func:`guest_merge.release_source` (``dropped`` +
``superseded_by``; heç nə silinmir). Başqa forma (iki öz sətir, iki qonaq, xanalı öz sətir) toxunulmur — sayılır.

``sibling`` — **eyni dərsin xanası tələbənin başqa (tarixçə) qeydiyyatındadır.** Boş xana üçün tələbənin eyni fəndən
(səviyyə kohortunda — eyni səviyyə AİLƏSİNDƏN) BAŞQA qeydiyyatında eyni tarix + başlama saatı + dərs növü + EYNİ
müəllimin dərsində xana varsa, həmin xana bu boş xanaya köçürülür (``copy_mark``: status, bal, yazan müəllim, yaranma
vaxtı). Mənbə qeydiyyat aktiv dublikat ola bilməz (o hal ``dedupe``-dur); bir neçə fərqli dəyər → yazılmır
(``sibling_ambiguous``). Nümunələr: 2026-11-06 səviyyə kohortu qurularkən artıq ``dropped`` olmuş səviyyə sətirlərinin
xanaları; köçürülən tələbənin köhnə jurnalındakı eyni patok dərsi.

Ümumi qaydalar: yalnız cari semestr, aktiv və bağlı olmayan açılış, Kollec qrupları xaricdə (sahib 2026-11-10), dərs
tarixi bu gündən əvvəl, dərs tələbəyə aiddir (lab / seminar alt qrupu), xana BOŞDUR (kilid altında yenidən yoxlanılır).
Hər qaçış bir ``batch`` id-si ilə audit sətri yazır — ``undo(batch)`` YALNIZ həmin qaçışın yaratdığı (dəyişməmiş,
rəsmi düzəlişsiz) xanaları silir və azad edilmiş sətirləri bərpa edir. İdempotentdir: ikinci qaçışda iş yoxdur.
"""

from __future__ import annotations

import secrets
from collections import defaultdict

from django.apps import apps as django_apps
from django.db.models import Count
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from . import lab_groups
from .gradebook import lesson_allows_score
from .language_levels import is_level_subject, level_family
from .twin_relocate import closed, copy_mark, recompute_absences

REASON = "Sahib 2026-11-10: boş xanalar yalnız sistemdaxili mötəbər mənbədən (eyni dərsin xanası / dublikat qeydiyyat)"
UNDO_REASON = "Sahib 2026-11-10: boş xanaların doldurulmasının geri qaytarılması"
RESOURCE = "registrar.empty_cells_fill_2026_11_10"
OPS = ("dedupe", "sibling")


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"emptycells-{timezone.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _score(value):
    return None if value is None else str(float(value))


class Scope:
    """Cari semestrin aktiv, bağlı olmayan, Kollec olmayan açılışları + onların aktiv siyahısı."""

    def __init__(self, organization, *, today=None):
        from .college_journals_hide_2026_11_10 import college_group_ids

        Period, Offering = _model("AcademicPeriod", "organizations"), _model("CourseOffering")
        self.organization = organization
        self.today = today or timezone.localdate()
        self.period = (
            Period.objects.filter(organization=organization, is_current=True, is_active=True)
            .order_by("-start_date")
            .first()
        )
        rows = []
        if self.period is not None:
            college = college_group_ids(organization)
            rows = [
                row
                for row in Offering.objects.filter(organization=organization, period=self.period, is_active=True)
                .select_related("subject")
                .only("pk", "group_id", "subject_id", "subject__name", "instructor_id", "period_id", "organization_id")
                if str(row.group_id) not in college
            ]
        shut = closed([row.pk for row in rows])
        self.offerings = {row.pk: row for row in rows if str(row.pk) not in shut}
        self.cohorts = set(
            _model("LanguageLevelCohort")
            .objects.filter(organization=organization, offering_id__in=list(self.offerings))
            .values_list("offering_id", flat=True)
        )


# ── dedupe ────────────────────────────────────────────────────────────────────


def dedupe(scope, *, counts, manifest, actor) -> None:
    from .guest_merge import release_block_reason, release_source

    Enrollment, LessonMark = _model("Enrollment"), _model("LessonMark")
    rows = list(
        Enrollment.objects.filter(
            organization=scope.organization,
            offering_id__in=list(scope.offerings),
            status="enrolled",
            superseded_by__isnull=True,
        ).values_list("pk", "student_id", "offering_id", "source_group_id")
    )
    groups = defaultdict(list)
    for pk, student_id, offering_id, source_group_id in rows:
        groups[(student_id, scope.offerings[offering_id].subject_id)].append((pk, source_group_id))
    duplicates = {key: items for key, items in groups.items() if len(items) > 1}
    if not duplicates:
        return
    ids = [pk for items in duplicates.values() for pk, _ in items]
    marks = dict(
        LessonMark.objects.filter(enrollment_id__in=ids)
        .values("enrollment_id")
        .annotate(n=Count("id"))
        .values_list("enrollment_id", "n")
    )
    scored = set()
    for name in ("ComponentScore", "ExamScoreEntry", "SelfWorkMark"):
        scored |= set(_model(name).objects.filter(enrollment_id__in=ids).values_list("enrollment_id", flat=True))
    objects = (
        Enrollment.objects.select_for_update(of=("self",))
        .select_related("offering", "offering__group", "offering__subject", "student")
        .in_bulk(ids)
    )
    for key in sorted(duplicates, key=lambda k: (k[0], str(k[1]))):
        items = duplicates[key]
        own = [pk for pk, source_group in items if source_group is None]
        guests = [pk for pk, source_group in items if source_group is not None and marks.get(pk)]
        counts["dedupe_pairs_seen"] += 1
        if len(own) != 1 or len(items) != 2 or len(guests) != 1:
            counts["dedupe_shape_kept"] += 1
            continue
        source, target = objects[own[0]], objects[guests[0]]
        if marks.get(source.pk) or source.pk in scored:
            counts["dedupe_own_has_data_kept"] += 1
            continue
        if source.status != "enrolled" or target.status != "enrolled" or release_block_reason(source):
            counts["dedupe_release_blocked"] += 1
            continue
        release_source(source=source, target=target, by_user=actor, reason=REASON)
        manifest["released"].append({"source": str(source.pk), "target": str(target.pk)})
        counts["dedupe_released"] += 1


# ── sibling ───────────────────────────────────────────────────────────────────


def _family_key(subject_name):
    return ("family", level_family(subject_name)) if is_level_subject(subject_name) else None


def sibling(scope, *, counts, manifest) -> None:
    Lesson, Enrollment, LessonMark = _model("Lesson"), _model("Enrollment"), _model("LessonMark")
    offerings = scope.offerings
    lessons = list(
        Lesson.objects.filter(
            organization=scope.organization, offering_id__in=list(offerings), date__lt=scope.today
        ).only("pk", "offering_id", "date", "start_time", "kind", "instructor_id", "lab_group", "seminar_group")
    )
    if not lessons:
        return
    roster = defaultdict(list)
    for enrollment in Enrollment.objects.select_for_update(of=("self",)).filter(
        organization=scope.organization, offering_id__in=list(offerings), status="enrolled", superseded_by__isnull=True
    ):
        roster[enrollment.offering_id].append(enrollment)
    filled = set(
        LessonMark.objects.filter(lesson_id__in=[row.pk for row in lessons]).values_list("lesson_id", "enrollment_id")
    )
    empty = []  # (lesson, enrollment)
    for lesson in lessons:
        for enrollment in roster.get(lesson.offering_id, ()):
            if (lesson.pk, enrollment.pk) not in filled and lab_groups.applies(lesson, enrollment):
                empty.append((lesson, enrollment))
    counts["sibling_empty_cells_seen"] += len(empty)
    if not empty:
        return
    students = {enrollment.student_id for _, enrollment in empty}
    # Tələbələrin bu semestrdəki BÜTÜN qeydiyyatlarının xanaları (eyni fənn və ya eyni səviyyə ailəsi süzgəci aşağıda).
    active_ids = {e.pk for rows in roster.values() for e in rows}
    source_marks = defaultdict(list)  # (student, date, start, kind, teacher) → [(subject_key, mark)]
    for mark in (
        LessonMark.objects.filter(
            organization=scope.organization,
            enrollment__student_id__in=students,
            lesson__offering__period_id=scope.period.pk,
        )
        .exclude(enrollment_id__in=active_ids)
        .select_related("lesson__offering__subject", "enrollment")
    ):
        source = mark.lesson
        teacher = source.instructor_id or source.offering.instructor_id
        key = (mark.enrollment.student_id, source.date, source.start_time, source.kind, teacher)
        source_marks[key].append((source.offering.subject_id, _family_key(source.offering.subject.name), mark))
    touched = {}
    for lesson, enrollment in empty:
        offering = offerings[lesson.offering_id]
        teacher = lesson.instructor_id or offering.instructor_id
        family = _family_key(offering.subject.name) if lesson.offering_id in scope.cohorts else None
        hits = [
            mark
            for subject_id, source_family, mark in source_marks.get(
                (enrollment.student_id, lesson.date, lesson.start_time, lesson.kind, teacher), ()
            )
            if subject_id == offering.subject_id or (family is not None and source_family == family)
        ]
        if not hits:
            continue
        values = {(mark.status, _score(mark.score)) for mark in hits}
        if len(values) != 1:
            counts["sibling_ambiguous"] += 1
            continue
        mark = hits[0]
        if mark.score is not None and not lesson_allows_score(lesson):
            counts["sibling_score_not_allowed"] += 1
            continue
        if LessonMark.objects.filter(lesson=lesson, enrollment=enrollment).exists():  # kilid altında yenidən
            counts["sibling_already_filled"] += 1
            continue
        created = copy_mark(mark, lesson=lesson, enrollment=enrollment)
        manifest["marks_created"].append({"id": str(created.pk), "status": created.status, "score": _score(mark.score)})
        touched[enrollment.pk] = enrollment
        counts["sibling_filled"] += 1
        counts[f"sibling_filled_{created.status}"] += 1
        counts["sibling_filled_cohort" if lesson.offering_id in scope.cohorts else "sibling_filled_regular"] += 1
    recompute_absences(list(touched.values()))


# ── giriş ────────────────────────────────────────────────────────────────────


def run(*, organization, actor, counts, ops=OPS, batch=None, today=None) -> str:
    batch = batch or new_batch()
    scope = Scope(organization, today=today)
    if scope.period is None:
        counts["period_missing"] += 1
        return batch
    counts["offerings_in_scope"] += len(scope.offerings)
    manifest = {"released": [], "marks_created": []}
    if "dedupe" in ops:
        dedupe(scope, counts=counts, manifest=manifest, actor=actor)
    if "sibling" in ops:
        sibling(scope, counts=counts, manifest=manifest)
    if manifest["released"] or manifest["marks_created"]:
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            new_values={"released": len(manifest["released"]), "cells": len(manifest["marks_created"])},
            changes=manifest,
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=batch,
        )
    return batch


def undo(*, organization, actor, counts, batch) -> None:
    AuditLog, Enrollment, LessonMark = _model("AuditLog", "audit"), _model("Enrollment"), _model("LessonMark")
    JournalCorrection = _model("JournalCorrection")
    rows = list(
        AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, reason=REASON, resource_id=batch)
    )
    if not rows:
        counts["undo_batch_unknown"] += 1
        return
    for row in rows:
        changes = row.changes or {}
        items = {item["id"]: item for item in changes.get("marks_created") or []}
        corrected = set(
            JournalCorrection.objects.filter(lesson_mark_id__in=list(items), reversal__isnull=True).values_list(
                "lesson_mark_id", flat=True
            )
        )
        enrollments = {}
        for mark in LessonMark.objects.select_related("enrollment").filter(pk__in=list(items)):
            item = items[str(mark.pk)]
            if mark.pk in corrected or (mark.status, _score(mark.score)) != (item["status"], item["score"]):
                counts["undo_cells_changed_kept"] += 1
                continue
            enrollments[mark.enrollment_id] = mark.enrollment
            mark.delete()
            counts["undo_cells_deleted"] += 1
        recompute_absences(list(enrollments.values()))
        for item in changes.get("released") or []:
            source = Enrollment.objects.select_for_update(of=("self",)).filter(pk=item["source"]).first()
            if source is None or source.status != "dropped" or str(source.superseded_by_id) != item["target"]:
                counts["undo_release_changed_kept"] += 1
                continue
            source.superseded_by = None
            source.status = "enrolled"
            source.save(update_fields=["status", "superseded_by", "updated_at"])
            counts["undo_released_restored"] += 1
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            new_values={"undo": True},
            reason=UNDO_REASON,
            resource_type=RESOURCE,
            resource_id=batch,
        )


__all__ = ["OPS", "REASON", "RESOURCE", "new_batch", "run", "undo"]
