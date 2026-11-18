"""MR-000504 (2026-11-18): 434 R «İXD-3» — 5 köhnə dərsin Günayın tələbələrinə aid xanaları onun 434 R-2 jurnalına.

İki yarım qrup eyni saatlarda paralel keçirdi; köhnə sistem delta-sı hər iki müəllimin dərslərini bir açılışa yığdı.
12.11-də jurnal bölünəndə (``split_share_journal_20261112``) Yeganənin adına yazılmış 5 dərs ana jurnalda qaldı,
Günayın 9 tələbəsinin həmin dərslərdəki xanaları isə düşürülmüş (``dropped``) qeydiyyatlarda gizli qaldı. 18.11-də
həmin dərslər Günayın jurnalına əl ilə əlavə edildi (boş) — bu əmr xanaları köçürür.

Qaydalar (hər şey kilid altında yenidən yoxlanılır):

* mənbə və hədəf açılış eyni fənn; hədəf aktiv və bağlı deyil; hər cütdə dərslər öz açılışına aiddir və tarixi eynidir;
* yalnız hədəfdə ``enrolled`` olan tələbələrin mənbə dərsdəki xanası köçürülür (mənbə qeydiyyatın statusu fərq etmir);
* hədəfdə həmin dərsdə artıq xana varsa — toxunulmur (müəllimin öz yazısı üstündür);
* mənbədəki xana SİLİNMİR (Yeganənin jurnalında gizli qeydiyyatdır, heç yerdə sayılmır);
* qayıb saatı hədəf qeydiyyatlar üçün yenidən hesablanır; audit sətrində ``batch`` + yaradılan xana id-ləri.

``undo`` — yalnız həmin ``batch``-ın yaratdığı xanaları silir.
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

RESOURCE = "registrar.share_marks_copy_20261118"
REASON = "MR-000504: 434 R — paralel yarım qrupun 5 köhnə dərsinin xanaları müəllimin öz jurnalına köçürüldü"
UNDO_REASON = "MR-000504: xana köçürməsinin geri qaytarılması"

SOURCE_OFFERING = "dee9eb13-fbec-49e4-9178-0c3fda81bf94"  # 434 R İXD-3 (Yeganə Hidayətova)
TARGET_OFFERING = "74c9e377-17b8-48ee-b58c-08750524e915"  # 434 R-2 (Günay Əmirova)
#: (mənbə dərs, hədəf dərs) — 16.09, 17.09 10:10, 17.09 11:50, 23.09, 08.10 10:10.
LESSON_PAIRS = (
    ("7fd9e8d6-08be-485c-a6fd-534ec934e3c1", "acb67d95-5d7f-4e79-9dd7-80e1c30a531b"),
    ("b71b7cd0-58d2-40ec-96f2-a7ffb9119ebf", "d3ddf029-fe94-42e6-9735-1758acd6a15a"),
    ("498670f9-e7ea-45b3-a40f-d53056f582de", "a0efd914-6279-41f4-999c-463ced746ff8"),
    ("19faa3ca-91e1-45f9-8d84-8a46c39699e3", "b5dd0d38-02c0-43bb-8faf-2c86f6ac68e4"),
    ("45a4900f-11f5-47d5-b309-ee8da3dd5cc8", "8a28d9a2-85d7-49e2-8cc6-8955b9f7de68"),
)


def _model(name: str):
    return django_apps.get_model("registrar", name)


def new_batch() -> str:
    return f"shmarks-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def run(*, organization, actor, counts: Counter, batch: str, source=None, target=None, pairs=None) -> str:
    from core.rls import journal_unlock

    batch = batch or new_batch()
    source, target = source or SOURCE_OFFERING, target or TARGET_OFFERING
    CourseOffering = _model("CourseOffering")
    Enrollment = _model("Enrollment")
    Lesson = _model("Lesson")
    LessonMark = _model("LessonMark")
    offerings = {
        str(row.pk): row
        for row in CourseOffering.objects.select_for_update().filter(organization=organization, pk__in=[source, target])
    }
    src, dst = offerings.get(str(source)), offerings.get(str(target))
    if src is None or dst is None or src.subject_id != dst.subject_id:
        counts["offering_invalid"] += 1
        return batch
    if not dst.is_active or closed([dst.pk]):
        counts["target_closed"] += 1
        return batch
    targets = {row.student_id: row for row in Enrollment.objects.filter(offering=dst, status="enrolled")}
    counts["target_students"] = len(targets)
    created, touched = [], {}
    with transaction.atomic(), journal_unlock(local=True):
        for source_lesson_id, target_lesson_id in LESSON_PAIRS if pairs is None else pairs:
            lessons = {
                str(row.pk): row
                for row in Lesson.objects.select_for_update().filter(pk__in=[source_lesson_id, target_lesson_id])
            }
            s_lesson, t_lesson = lessons.get(str(source_lesson_id)), lessons.get(str(target_lesson_id))
            if (
                s_lesson is None
                or t_lesson is None
                or s_lesson.offering_id != src.pk
                or t_lesson.offering_id != dst.pk
                or s_lesson.date != t_lesson.date
            ):
                counts["lesson_pair_invalid"] += 1
                continue
            counts["lesson_pairs_ok"] += 1
            filled = set(LessonMark.objects.filter(lesson=t_lesson).values_list("enrollment_id", flat=True))
            marks = LessonMark.objects.filter(
                lesson=s_lesson, enrollment__offering=src, enrollment__student_id__in=list(targets)
            ).select_related("enrollment")
            for mark in marks:
                enrollment = targets[mark.enrollment.student_id]
                if enrollment.pk in filled:
                    counts["target_cell_kept"] += 1
                    continue
                new = copy_mark(mark, lesson=t_lesson, enrollment=enrollment)
                created.append(str(new.pk))
                touched[enrollment.pk] = enrollment
                counts[f"marks_copied_{mark.status}"] += 1
                counts["marks_copied"] += 1
        if not created:
            counts["nothing_to_copy"] += 1
            return batch
        recompute_absences(list(touched.values()))
        counts["enrollments_recomputed"] = len(touched)
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=REASON,
            resource_type=RESOURCE,
            resource_id=str(dst.pk),
            resource_repr="Paralel yarım qrupun köhnə dərs xanaları müəllimin jurnalına",
            old_values={"source_offering": str(src.pk)},
            new_values={"batch": batch, "target_offering": str(dst.pk), "marks_created": created},
        )
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    from core.rls import journal_unlock

    AuditLog = django_apps.get_model("audit", "AuditLog")
    Enrollment = _model("Enrollment")
    LessonMark = _model("LessonMark")
    rows = AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, new_values__batch=batch)
    with transaction.atomic(), journal_unlock(local=True):
        for row in rows:
            counts["undo_rows"] += 1
            marks = LessonMark.objects.filter(pk__in=(row.new_values or {}).get("marks_created") or [])
            enrollment_ids = set(marks.values_list("enrollment_id", flat=True))
            counts["undo_marks_deleted"] += marks.count()
            marks.delete()
            recompute_absences(list(Enrollment.objects.filter(pk__in=enrollment_ids)))
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                reason=UNDO_REASON,
                resource_type=f"{RESOURCE}.undo",
                resource_id=row.resource_id,
                resource_repr="Xana köçürməsinin geri qaytarılması",
                old_values={"batch": batch},
                new_values={"undone_batch": batch},
            )


__all__ = ["LESSON_PAIRS", "RESOURCE", "SOURCE_OFFERING", "TARGET_OFFERING", "run", "undo"]
