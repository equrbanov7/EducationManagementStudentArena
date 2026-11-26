"""``split_shared_lessons_20261126 --undo --batch lsplit-…`` — :mod:`.lesson_split_2026_11_26` qaçışının geri qaytarılması.

Yalnız həmin ``batch``-ın audit sətirləri əsasında:

* surət dərsə köçmüş xanalar (köhnə → yeni id cütləri) əsl dərsə geri köçür (eyni ``status`` / ``score`` /
  ``entered_by`` / ``created_at`` / ``updated_at``); əsl dərsdə həmin tələbənin xanası artıq varsa toxunulmur (sayılır);
* xanası qalmayan surət dərs silinir; bölünmədən sonra yazılmış xanası olan surət SAXLANILIR (sayılır);
* dərslərin ``seminar_group``-u əvvəlki dəyərinə (boş) qayıdır; qaçışın yerləşdirdiyi tələbələrin alt qrupu təmizlənir;
* qaçışın yaratdığı ``SeminarGroup`` sətirləri — ona istinad qalmırsa — silinir;
* qayıb saatı xanası köçən qeydiyyatlar üçün yenidən hesablanır. İkinci ``undo`` heç nə yazmır.
"""

from __future__ import annotations

from collections import Counter

from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .lesson_split_2026_11_26 import RESOURCE, UNDO_REASON, _model, move_mark


def _undo_split(values, counts: Counter, touched: set) -> None:
    Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
    lesson = Lesson.objects.select_for_update().filter(pk=values.get("lesson")).first()
    clone = Lesson.objects.select_for_update().filter(pk=values.get("clone")).first()
    if lesson is None or clone is None:
        counts["undo_lesson_missing"] += 1
        return
    taken = set(LessonMark.objects.filter(lesson=lesson).values_list("enrollment_id", flat=True))
    for _old_id, new_id in values.get("marks") or []:
        mark = LessonMark.objects.select_for_update().filter(pk=new_id, lesson=clone).first()
        if mark is None:
            counts["undo_mark_missing"] += 1
            continue
        if mark.enrollment_id in taken:
            counts["undo_target_cell_filled_kept"] += 1
            continue
        move_mark(mark, lesson=lesson)
        taken.add(mark.enrollment_id)
        touched.add(mark.enrollment_id)
        counts["undo_marks_moved_back"] += 1
    if LessonMark.objects.filter(lesson=clone).exists():
        counts["undo_clone_kept_has_marks"] += 1
    else:
        Lesson.objects.filter(pk=clone.pk).delete()
        counts["undo_clones_deleted"] += 1


def _undo_sections(offering_id, values, counts: Counter) -> None:
    Enrollment, Lesson, SeminarGroup = _model("Enrollment"), _model("Lesson"), _model("SeminarGroup")
    for number, enrollment_ids in (values.get("placed") or {}).items():
        counts["undo_students_cleared"] += Enrollment.objects.filter(
            pk__in=enrollment_ids, seminar_group=int(number)
        ).update(seminar_group=None)
    for row in SeminarGroup.objects.select_for_update().filter(pk__in=values.get("created") or []):
        used = (
            Enrollment.objects.filter(offering_id=offering_id, seminar_group=row.number).exists()
            or Lesson.objects.filter(offering_id=offering_id, seminar_group=row.number).exists()
        )
        if used:
            counts["undo_section_kept_in_use"] += 1
            continue
        row.delete()
        counts["undo_sections_deleted"] += 1


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    AuditLog = _model("AuditLog", "audit")
    if AuditLog.objects.filter(
        organization=organization, resource_type=f"{RESOURCE}.undo", new_values__batch=batch
    ).exists():
        counts["undo_already_done"] += 1
        return
    rows = list(
        AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, new_values__batch=batch).order_by(
            "created_at"
        )
    )
    if not rows:
        counts["undo_batch_unknown"] += 1
        return
    Lesson = _model("Lesson")
    touched, sections, offering_id = set(), [], None
    for row in rows:
        values = row.new_values or {}
        counts["undo_rows"] += 1
        if values.get("op") == "sections":
            sections.append(values)
            offering_id = values.get("offering")
            continue
        if values.get("op") == "split":
            _undo_split(values, counts, touched)
        counts["undo_lessons_reset"] += Lesson.objects.filter(
            pk=values.get("lesson"), seminar_group=values.get("number")
        ).update(seminar_group=values.get("old_number"), updated_at=timezone.now())
    for values in sections:
        _undo_sections(offering_id, values, counts)
    if touched:
        from .gradebook import recompute_absence_hours_many

        recompute_absence_hours_many(list(_model("Enrollment").objects.filter(pk__in=touched)))
        counts["undo_absences_recomputed"] += len(touched)
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        reason=UNDO_REASON,
        resource_type=f"{RESOURCE}.undo",
        resource_id=str(offering_id or ""),
        resource_repr="Ortaq dərslərin bölünməsi geri qaytarıldı",
        old_values={},
        new_values={"batch": batch, "rows": counts["undo_rows"]},
    )


__all__ = ["undo"]
