"""İntensivə köçürmədə tələbənin dərsləri və xanaları yeni jurnala (MR-000379, 2026-11-16).

Səbəb: «Adi jurnaldan intensivə köçür» (:func:`apps.registrar.intensive.open_course`, ``release_source=True``) yalnız
yazılışı daşıyırdı — köhnə jurnalın dərsləri və tələbənin xanaları orada qalırdı. Köhnə jurnal tələbənin TƏK jurnalı
idisə (başqa tələbə qalmayıb), müəllim intensiv jurnalı boş görür: «bütün dərslər silinib». Bir dəfəlik düzəliş
əmri (:mod:`.intensive_lessons_carry_2026_11_16`, PR #371) iki cütü əl ilə köçürdü; bu modul eyni qaydanı köçürmə
anında tətbiq edir.

Qaydalar:

* yalnız köçürmədən sonra mənbə jurnalda HEÇ BİR ``enrolled`` tələbə qalmayıbsa — qrup jurnalının bütün dərsləri
  qısa intensiv kursa tökülmür (orada dərslər qrupundur, tələbənin işi əvvəlki kimi «əvvəlki jurnal» xülasəsi ilə
  görünür, ``guest_merge.carry_over_map``);
* mənbənin hər dərsi üçün hədəfdə eyni (tarix, başlama saatı, növ) dərs varsa o işlənir, yoxdursa SURƏTİ yaradılır
  (:data:`LESSON_COPY_FIELDS`; sillabus sətri bağlanmır); tələbənin hər xanası uyğun dərsə yeni sətir kimi yazılır
  (``created_at`` köhnəsi — redaktə pəncərəsi yenidən açılmır), hədəfdə artıq olan xanaya toxunulmur. Mənbə
  SİLİNMİR (köhnə jurnal tarixçə kimi qalır);
* qayıb İKİ DƏFƏ sayılmır: əvəzlənmiş yazılışın qayıbı hədəfə ``guest_merge.carried_absence_hours`` ilə gəlir, amma
  hədəfdə eyni (tarix, saat, növ) dərsinin xanası olan mənbə xanası o xəritədə sayılmır (``carry_over_map``);
* hər cüt üçün audit sətri (yaradılan dərs/xana id-ləri, ``batch``); intensiv kurs ləğv olunanda
  (:func:`undo_for_target`) yalnız bu köçürmənin yaratdığı xanalar və başqa xanası qalmayan dərslər silinir.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .twin_relocate import copy_mark, recompute_absences

RESOURCE = "registrar.intensive_move_carry"
REASON = "İntensivə köçürmə: tələbənin dərsləri və xanaları köhnə jurnaldan intensiv jurnala (MR-000379)"
UNDO_REASON = "İntensiv kurs ləğvi: köçürülmüş dərs və xanaların geri qaytarılması"

#: Dərs surətinə köçən sahələr (PR #371 əmri ilə eyni).
LESSON_COPY_FIELDS = (
    "date",
    "kind",
    "topic",
    "hours",
    "start_time",
    "end_time",
    "created_by_id",
    "instructor_id",
    "room_id",
    "is_legacy_synthesised",
    "lab_group",
    "seminar_group",
    "is_passive",
)


def _model(name: str):
    return django_apps.get_model("registrar", name)


def new_batch(prefix: str = "imove") -> str:
    return f"{prefix}-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def lesson_key(lesson) -> tuple:
    """Eyni dərsin açarı — (tarix, başlama saatı, növ)."""
    return (lesson.date, lesson.start_time, lesson.kind)


def copy_work(*, source, target, src_enrollment, dst_enrollment, counts: Counter) -> tuple[list, list]:
    """Mənbə açılışın dərsləri (yoxdursa surəti) + tələbənin xanaları hədəfə; ``(dərs_id-lər, xana_id-lər)``.

    Kilid və icazə yoxlaması çağıranındır (tranzaksiya içində). Sayğac açarları PR #371 əmri ilə eynidir."""
    Lesson = _model("Lesson")
    LessonMark = _model("LessonMark")
    existing: dict = {}
    for lesson in Lesson.objects.select_for_update().filter(offering=target):
        existing.setdefault(lesson_key(lesson), []).append(lesson)
    mapping, created_lessons = {}, []
    for lesson in Lesson.objects.filter(offering=source).order_by("date", "start_time", "created_at"):
        found = existing.get(lesson_key(lesson)) or []
        if len(found) > 1:
            counts["target_lesson_ambiguous"] += 1
            continue
        if found:
            mapping[lesson.pk] = found[0]
            counts["target_lesson_reused"] += 1
            continue
        copy = Lesson.objects.create(
            organization_id=target.organization_id,
            offering=target,
            **{field: getattr(lesson, field) for field in LESSON_COPY_FIELDS},
        )
        existing[lesson_key(copy)] = [copy]
        mapping[lesson.pk] = copy
        created_lessons.append(str(copy.pk))
    counts["lessons_created"] += len(created_lessons)
    filled = {
        str(pk)
        for pk in LessonMark.objects.filter(
            enrollment=dst_enrollment, lesson_id__in=[row.pk for row in mapping.values()]
        ).values_list("lesson_id", flat=True)
    }
    created_marks = []
    for mark in LessonMark.objects.filter(enrollment=src_enrollment).order_by("created_at", "pk"):
        lesson = mapping.get(mark.lesson_id)
        if lesson is None:
            counts["mark_without_target_lesson"] += 1
            continue
        if str(lesson.pk) in filled:
            counts["target_cell_filled_kept"] += 1
            continue
        copied = copy_mark(mark, lesson=lesson, enrollment=dst_enrollment)
        filled.add(str(lesson.pk))
        created_marks.append(str(copied.pk))
    counts["marks_copied"] += len(created_marks)
    return created_lessons, created_marks


def carry_on_move(*, organization, target, moved, by_user, counts: Counter | None = None, batch: str = "") -> dict:
    """``open_course`` köçürməsindən sonra: boş qalan mənbə jurnalların işi intensiv jurnala.

    ``moved`` — köçürülmüş hədəf yazılışları (``release_source`` ilə). Nəticə: ``{"batch", "lessons", "marks"}``."""
    Enrollment = _model("Enrollment")
    counts = Counter() if counts is None else counts
    batch = batch or new_batch()
    sources = list(
        Enrollment.objects.select_for_update(of=("self",))
        .filter(superseded_by__in=[row.pk for row in moved], status=Enrollment.Status.DROPPED)
        .select_related("offering")
    )
    by_target = {row.pk: row for row in moved}
    lessons = marks = 0
    touched = []
    for src_enrollment in sources:
        source = src_enrollment.offering
        if source.subject_id != target.subject_id:
            counts["source_other_subject"] += 1
            continue
        if Enrollment.objects.filter(offering=source, status=Enrollment.Status.ENROLLED).exists():
            counts["source_still_has_students"] += 1  # qrup jurnalı — dərslər qrupundur, köçürülmür
            continue
        dst_enrollment = by_target[src_enrollment.superseded_by_id]
        created_lessons, created_marks = copy_work(
            source=source, target=target, src_enrollment=src_enrollment, dst_enrollment=dst_enrollment, counts=counts
        )
        if not created_lessons and not created_marks:
            continue
        lessons += len(created_lessons)
        marks += len(created_marks)
        touched.append(dst_enrollment)
        log_action(
            AuditAction.UPDATE,
            user=by_user,
            organization=organization,
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(dst_enrollment.pk),
            resource_repr="İntensiv jurnala dərs və xana köçürülməsi",
            old_values={"source_offering": str(source.pk), "source_enrollment": str(src_enrollment.pk)},
            new_values={
                "batch": batch,
                "target_offering": str(target.pk),
                "lessons_created": created_lessons,
                "marks_created": created_marks,
            },
        )
    recompute_absences(touched)
    return {"batch": batch, "lessons": lessons, "marks": marks}


def undo_for_target(*, offering, by_user, counts: Counter | None = None) -> int:
    """Bu intensiv jurnala köçürmə ilə gələn xanaları və (başqa xanası qalmayan) dərsləri sil; silinən dərs sayı."""
    from core.rls import journal_unlock

    AuditLog = django_apps.get_model("audit", "AuditLog")
    Lesson = _model("Lesson")
    LessonMark = _model("LessonMark")
    Enrollment = _model("Enrollment")
    counts = Counter() if counts is None else counts
    rows = AuditLog.objects.filter(
        organization_id=offering.organization_id, resource_type=RESOURCE, new_values__target_offering=str(offering.pk)
    ).order_by("-created_at", "pk")
    deleted = 0
    with journal_unlock(local=True):
        for row in rows:
            values = row.new_values or {}
            marks = LessonMark.objects.filter(pk__in=values.get("marks_created") or [], lesson__offering=offering)
            enrollment_ids = set(marks.values_list("enrollment_id", flat=True))
            counts["undo_marks_deleted"] += marks.count()
            marks.delete()
            doomed = Lesson.objects.filter(
                pk__in=values.get("lessons_created") or [], offering=offering, marks__isnull=True
            )
            count = doomed.count()
            doomed.delete()
            deleted += count
            recompute_absences(list(Enrollment.objects.filter(pk__in=enrollment_ids)))
            log_action(
                AuditAction.UPDATE,
                user=by_user,
                organization=offering.organization,
                reason=UNDO_REASON,
                resource_type=f"{RESOURCE}.undo",
                resource_id=row.resource_id,
                resource_repr="İntensiv jurnala köçürmənin geri qaytarılması",
                old_values={"batch": values.get("batch", "")},
                new_values={"undone_batch": values.get("batch", ""), "lessons_deleted": count},
            )
    counts["undo_lessons_deleted"] += deleted
    return deleted


__all__ = ["LESSON_COPY_FIELDS", "RESOURCE", "carry_on_move", "copy_work", "lesson_key", "undo_for_target"]
