"""MR-000379 (Günel Rəhimli, 2026-11-16) — intensivə köçürülmüş tələbənin dərsləri və xanaları yeni jurnala.

Səbəb: 05.11 (MR-000182) «Tədqiqat metodları» və «Tarix elminin müasir problemləri» üçün 15 saatlıq İNTENSİV
jurnallar açıldı və tələbə onlara köçürüldü. Köçürmə YALNIZ yazılışı daşıdı: köhnə 206/6OT jurnallarındakı dərslər
(4 köhnə sistem dərsi + müəllimin 26.10 / 28.10 dərsləri) və tələbənin xanaları köhnə jurnalda qaldı. Köhnə jurnalda
indi tələbə yoxdur, intensiv jurnal isə boş görünür — müəllim «bütün dərslər silinib» yazır.

Cüt başına (sabit id-lər, şəxsi məlumat yoxdur; hər cüt öz savepoint-ində, HƏR ŞEY kilid altında yoxlanılır):

* mənbə və hədəf açılış mövcud, eyni fənn, hədəf aktiv və bağlı deyil; hədəfdə tələbənin ``enrolled`` yazılışı,
  mənbədə isə HƏMİN tələbənin (statusundan asılı olmayaraq) yazılışı var — yoxdursa cüt atlanır və sayılır;
* mənbənin hər dərsi üçün hədəfdə eyni (tarix, başlama saatı, növ) dərs varsa o işlənir, yoxdursa SURƏTİ yaradılır
  (tarix, növ, mövzu, saat, otaq, dərs müəllimi, yaradan, köçürmə nişanı eynidir; sillabus sətri bağlanmır);
* tələbənin mənbədəki hər xanası hədəfin uyğun dərsinə YENİ sətir kimi yazılır (``created_at`` köhnə xananınkı —
  15 dəqiqəlik pəncərə yenidən açılmır); hədəfdə həmin dərs üçün xana artıq varsa toxunulmur. Mənbə xanası
  SİLİNMİR (köhnə jurnal tarixçə kimi qalır);
* mənbə yazılışı hədəf yazılışı ilə əvəzlənmişdirsə (``superseded_by``) və mənbədə qayıb varsa, qayıb iki dəfə
  sayılmasın deyə cüt atlanır (``absence_double_risk``);
* sonda hədəf yazılışının qayıb saatı yenidən hesablanır; hər cüt üçün audit sətri (yaradılan dərs və xana id-ləri,
  ``batch``). ``undo`` yalnız həmin batch-in yaratdığı, dəyişməmiş xanaları və başqa xanası qalmayan yaradılmış
  dərsləri silir.

İdempotentdir: ikinci qaçışda dərslər tapılır, xanalar artıq doludur → 0 yazı.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .twin_relocate import closed, copy_mark, recompute_absences

RESOURCE = "registrar.intensive_lessons_carry"
REASON = "MR-000379: intensivə köçürülmüş tələbənin dərsləri və xanaları köhnə jurnaldan intensiv jurnala"
UNDO_REASON = "MR-000379: köçürmənin geri qaytarılması"

#: (mənbə açılış — köhnə 206/6OT jurnalı, hədəf açılış — 05.11-də açılmış intensiv jurnal).
PAIRS = (
    ("fb62b4ed-5fd7-4634-b6b6-d4496e01a5c1", "c5114ea7-8639-44b0-b72d-b436fc468ed2"),  # Tədqiqat metodları
    ("580bc433-3178-4c3e-b9e2-5fbee2d639f6", "4ff7d2fd-d970-4922-9ade-f9f9c6c3b280"),  # Tarix elminin müasir probl.
)

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


def new_batch() -> str:
    return f"icarry-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _lesson_key(lesson) -> tuple:
    return (lesson.date, lesson.start_time, lesson.kind)


def run(*, organization, actor, counts: Counter, batch: str, pairs=None) -> str:
    batch = batch or new_batch()
    for source_id, target_id in PAIRS if pairs is None else pairs:
        counts["pairs_in_plan"] += 1
        with transaction.atomic():
            _pair(organization, actor, counts, batch, source_id, target_id)
    return batch


def _pair(organization, actor, counts, batch, source_id, target_id) -> None:
    CourseOffering = _model("CourseOffering")
    Enrollment = _model("Enrollment")
    Lesson = _model("Lesson")
    LessonMark = _model("LessonMark")
    offerings = {
        str(row.pk): row
        for row in CourseOffering.objects.select_for_update().filter(
            organization=organization, pk__in=[source_id, target_id]
        )
    }
    source, target = offerings.get(str(source_id)), offerings.get(str(target_id))
    if source is None or target is None or source.subject_id != target.subject_id:
        counts["pair_offering_invalid"] += 1
        return
    if not target.is_active or closed([target.pk]):
        counts["pair_target_closed"] += 1
        return
    targets = list(Enrollment.objects.select_for_update().filter(offering=target, status="enrolled"))
    by_student = {
        row.student_id: row
        for row in Enrollment.objects.select_for_update().filter(
            offering=source, student_id__in=[row.student_id for row in targets]
        )
    }
    pairs = [(by_student[row.student_id], row) for row in targets if row.student_id in by_student]
    if len(pairs) != 1:
        counts["pair_student_unresolved"] += 1
        return
    src_enrollment, dst_enrollment = pairs[0]
    source_marks = list(LessonMark.objects.filter(enrollment=src_enrollment).select_related("lesson"))
    if src_enrollment.superseded_by_id == dst_enrollment.pk and any(m.status == "absent" for m in source_marks):
        counts["absence_double_risk"] += 1
        return
    existing = {}
    for lesson in Lesson.objects.select_for_update().filter(offering=target):
        existing.setdefault(_lesson_key(lesson), []).append(lesson)
    mapping, created_lessons = {}, []
    for lesson in Lesson.objects.filter(offering=source).order_by("date", "start_time", "created_at"):
        found = existing.get(_lesson_key(lesson)) or []
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
        existing[_lesson_key(copy)] = [copy]
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
    for mark in source_marks:
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
    if not created_lessons and not created_marks:
        counts["pair_already_done"] += 1
        return
    recompute_absences([dst_enrollment])
    counts["pairs_applied"] += 1
    log_action(
        AuditAction.UPDATE,
        user=actor,
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


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    from core.rls import journal_unlock

    AuditLog = django_apps.get_model("audit", "AuditLog")
    Lesson = _model("Lesson")
    LessonMark = _model("LessonMark")
    Enrollment = _model("Enrollment")
    rows = AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, new_values__batch=batch).order_by(
        "-created_at", "pk"
    )
    with journal_unlock(local=True):
        for row in rows:
            values = row.new_values or {}
            counts["undo_rows"] += 1
            marks = LessonMark.objects.filter(pk__in=values.get("marks_created") or [])
            counts["undo_marks_deleted"] += marks.count()
            enrollment_ids = set(marks.values_list("enrollment_id", flat=True))
            marks.delete()
            doomed = Lesson.objects.filter(pk__in=values.get("lessons_created") or [], marks__isnull=True)
            counts["undo_lessons_deleted"] += doomed.count()
            doomed.delete()
            recompute_absences(list(Enrollment.objects.filter(pk__in=enrollment_ids)))
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                reason=UNDO_REASON,
                resource_type=f"{RESOURCE}.undo",
                resource_id=row.resource_id,
                resource_repr="İntensiv jurnala köçürmənin geri qaytarılması",
                old_values={"batch": batch},
                new_values={"undone_batch": batch},
            )
