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
  (:data:`LESSON_COPY_FIELDS`; sillabus sətri bağlanmır); köhnə jurnal tarixçə kimi qalır;
* tələbənin xanaları KÖÇÜR: hədəf dərsə surət (bal, q/b, yazan, ``created_at`` — redaktə pəncərəsi yenidən açılmır),
  sonra köhnə jurnaldakı sətir silinir. Surət saxlanmır, çünki əvəzlənmiş yazılışın qayıbı hədəfə
  ``guest_merge.carried_absence_hours`` ilə onsuz da sayılır (DB qoruyucusu ``registrar_absence_credit_guard`` da eyni
  düsturu yoxlayır) — iki nüsxə qayıbı İKİ DƏFƏ sayardı. Xananın ``lesson_id``-si DB-də dəyişməzdir
  (``registrar_guard_reference_identity``), ona görə ``UPDATE`` yox, surət + silmə;
* köhnə yazılışın qayıb krediti (``AbsenceCredit``) və ya xanalarından birinin rəsmi düzəlişi (``JournalCorrection``)
  varsa xanalar köçmür (kredit/düzəliş izi həmin sətirlərə bağlıdır); dərslər yenə gəlir, iş əvvəlki kimi «əvvəlki
  jurnal» xülasəsində görünür;
* hər cüt üçün audit sətri (yaradılan dərslər, köçən xanalar və onların köhnə dərsi, ``batch``); intensiv kurs ləğv
  olunanda (:func:`undo_for_target`) xanalar köhnə yerinə qayıdır, başqa xanası qalmayan surət dərslər silinir.
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


def map_lessons(*, source, target, counts: Counter) -> tuple[dict, list]:
    """Mənbə dərsi → hədəfdəki eyni dərs (yoxdursa yaradılmış surəti); ``({mənbə_id: hədəf_dərs}, yaradılan_id-lər)``."""
    Lesson = _model("Lesson")
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
    return mapping, created_lessons


def _target_marks(mapping, dst_enrollment) -> set:
    LessonMark = _model("LessonMark")
    return {
        str(pk)
        for pk in LessonMark.objects.filter(
            enrollment=dst_enrollment, lesson_id__in=[row.pk for row in mapping.values()]
        ).values_list("lesson_id", flat=True)
    }


def copy_work(*, source, target, src_enrollment, dst_enrollment, counts: Counter) -> tuple[list, list]:
    """PR #371 əmri: dərslər + tələbənin xanalarının SURƏTİ (mənbə xanası qalır); ``(dərs_id-lər, xana_id-lər)``.

    Kilid və icazə yoxlaması çağıranındır (tranzaksiya içində)."""
    LessonMark = _model("LessonMark")
    mapping, created_lessons = map_lessons(source=source, target=target, counts=counts)
    filled = _target_marks(mapping, dst_enrollment)
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


def move_marks(*, mapping, src_enrollment, dst_enrollment, counts: Counter) -> list:
    """Tələbənin mənbə xanalarını hədəf dərslərə KÖÇÜR (surət + köhnə sətrin silinməsi);
    ``[{"mark": yeni_id, "from_lesson": köhnə_dərs_id}]``."""
    from core.rls import journal_unlock

    LessonMark = _model("LessonMark")
    filled = _target_marks(mapping, dst_enrollment)
    moved = []
    with journal_unlock(local=True):  # 15 dəqiqəlik xana kilidi: rəsmi köçürmə yolu (dəyər dəyişmir)
        for mark in LessonMark.objects.select_for_update().filter(enrollment=src_enrollment).order_by("created_at"):
            lesson = mapping.get(mark.lesson_id)
            if lesson is None:
                counts["mark_without_target_lesson"] += 1
                continue
            if str(lesson.pk) in filled:
                counts["target_cell_filled_kept"] += 1
                continue
            copied = copy_mark(mark, lesson=lesson, enrollment=dst_enrollment)
            moved.append({"mark": str(copied.pk), "from_lesson": str(mark.lesson_id)})
            filled.add(str(lesson.pk))
            mark.delete()
    counts["marks_moved"] += len(moved)
    return moved


def _marks_pinned(src_enrollment) -> bool:
    """Köhnə yazılışın xanaları yerində qalmalıdır: qayıb krediti və ya rəsmi xana düzəlişi var."""
    if _model("AbsenceCredit").objects.filter(enrollment=src_enrollment).exists():
        return True
    return _model("JournalCorrection").objects.filter(lesson_mark__enrollment=src_enrollment).exists()


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
        mapping, created_lessons = map_lessons(source=source, target=target, counts=counts)
        moved_marks = []
        if _marks_pinned(src_enrollment):
            counts["source_marks_pinned"] += 1  # kredit / rəsmi düzəliş həmin sətirlərdədir — xanalar yerində qalır
        else:
            moved_marks = move_marks(
                mapping=mapping, src_enrollment=src_enrollment, dst_enrollment=dst_enrollment, counts=counts
            )
        if not created_lessons and not moved_marks:
            continue
        lessons += len(created_lessons)
        marks += len(moved_marks)
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
                "marks_moved": moved_marks,
            },
        )
    recompute_absences(touched)
    return {"batch": batch, "lessons": lessons, "marks": marks}


def undo_for_target(*, offering, by_user, counts: Counter | None = None) -> int:
    """Bu intensiv jurnala köçən xanaları köhnə dərsinə + köhnə yazılışına qaytar, başqa xanası qalmayan surət
    dərsləri sil; silinən dərs sayı. Yalnız hələ bu jurnalda olan xanalar qaytarılır (sonradan köçürülməyənlər)."""
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
            source_enrollment = (row.old_values or {}).get("source_enrollment")
            returned = 0
            back = Enrollment.objects.filter(pk=source_enrollment).first()
            for item in values.get("marks_moved") or []:
                mark = LessonMark.objects.filter(pk=item.get("mark"), lesson__offering=offering).first()
                home = Lesson.objects.filter(pk=item.get("from_lesson")).first()
                if mark is None or home is None or back is None:
                    counts["undo_mark_missing"] += 1
                    continue
                if not LessonMark.objects.filter(lesson=home, enrollment=back).exists():
                    copy_mark(mark, lesson=home, enrollment=back)
                mark.delete()
                returned += 1
            counts["undo_marks_returned"] += returned
            doomed = Lesson.objects.filter(
                pk__in=values.get("lessons_created") or [], offering=offering, marks__isnull=True
            )
            count = doomed.count()
            doomed.delete()
            deleted += count
            recompute_absences(
                list(Enrollment.objects.filter(pk__in=[source_enrollment, row.resource_id]).exclude(pk=None))
            )
            log_action(
                AuditAction.UPDATE,
                user=by_user,
                organization=offering.organization,
                reason=UNDO_REASON,
                resource_type=f"{RESOURCE}.undo",
                resource_id=row.resource_id,
                resource_repr="İntensiv jurnala köçürmənin geri qaytarılması",
                old_values={"batch": values.get("batch", "")},
                new_values={
                    "undone_batch": values.get("batch", ""),
                    "lessons_deleted": count,
                    "marks_returned": returned,
                },
            )
    counts["undo_lessons_deleted"] += deleted
    return deleted


__all__ = [
    "LESSON_COPY_FIELDS",
    "RESOURCE",
    "carry_on_move",
    "copy_work",
    "lesson_key",
    "map_lessons",
    "move_marks",
    "undo_for_target",
]
