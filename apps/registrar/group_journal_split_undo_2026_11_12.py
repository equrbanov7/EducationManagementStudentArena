"""``split_group_journal_20261112 --undo`` — qrup jurnalı ayrılmasını geri qaytarmaq (YALNIZ audit manifesti).

Ayrılmadan SONRA hədəf jurnalda müəllimin yazdığı data varsa (yeni dərs / xana / bal, kopyalanmış xananın və ya
balın dəyişməsi, yekun nəticə) geri qaytarılmır — ``undo_blocked_post_split_data`` (müəllimin yazdığı itməsin).
Ardıcıllıq: mənbədə silinmiş dərslər EYNİ id ilə xanaları ilə bərpa → mənbə qeydiyyatları ``enrolled`` → hədəfin
balları, xanaları, dərsləri, yaradılmış komponentləri, slotları silinir → hədəf qeydiyyatları silinir (yaradılıbsa)
və ya əvvəlki statusuna qaytarılır. Hədəf jurnalın özü (mövcud idi) qalır.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .group_journal_split_2026_11_12 import GROUP, RESOURCE, SOURCE, TARGET, applied_batches
from .share_journal_split_undo_2026_11_12 import _restore_lessons
from .twin_relocate import recompute_absences

UNDO_REASON = "Sahib 2026-11-12 (MR-000317): qrup jurnalı ayrılmasının geri qaytarılması"
_AFTER_MODELS = ("FinalGrade", "CourseWork", "ResitRecord", "CriterionScore")


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def _post_split_data(target_id, since, manifest) -> bool:
    Lesson, LessonMark, Score = _model("Lesson"), _model("LessonMark"), _model("ComponentScore")
    lessons = set(manifest.get("lessons_created", []))
    marks = set(manifest.get("marks_created", []))
    scores = set(manifest.get("scores_created", []))
    rows = Lesson.objects.filter(offering_id=target_id)
    if any(str(pk) not in lessons for pk in rows.values_list("pk", flat=True)):
        return True
    if rows.filter(updated_at__gt=since).exclude(pk__in=lessons).exists():
        return True
    cells = LessonMark.objects.filter(lesson__offering_id=target_id)
    if any(str(pk) not in marks for pk in cells.values_list("pk", flat=True)):
        return True
    if cells.filter(updated_at__gt=since).exists():
        return True
    given = Score.objects.filter(enrollment__offering_id=target_id)
    if any(str(pk) not in scores for pk in given.values_list("pk", flat=True)):
        return True
    if given.filter(updated_at__gt=since).exists():
        return True
    return any(_model(name).objects.filter(enrollment__offering_id=target_id).exists() for name in _AFTER_MODELS)


def _drop_target(manifest, counts) -> None:
    get = manifest.get
    Enrollment = _model("Enrollment")
    counts["undo_scores_deleted"] += (
        _model("ComponentScore").objects.filter(pk__in=get("scores_created", [])).delete()[0]
    )
    counts["undo_marks_deleted"] += _model("LessonMark").objects.filter(pk__in=get("marks_created", [])).delete()[0]
    counts["undo_lessons_deleted"] += _model("Lesson").objects.filter(pk__in=get("lessons_created", [])).delete()[0]
    _model("AssessmentComponent").objects.filter(pk__in=get("components_created", [])).delete()
    _model("ScheduleSlot").all_objects.filter(pk__in=get("slots_created", [])).delete()
    counts["undo_target_enrollments_deleted"] += Enrollment.objects.filter(
        pk__in=get("enrollments_created", [])
    ).delete()[0]
    for row in get("enrollments_reactivated", []):
        Enrollment.objects.filter(pk=row["id"]).update(
            status=row["status"], superseded_by_id=row.get("superseded_by") or None, updated_at=timezone.now()
        )
        counts["undo_target_enrollments_restored"] += 1


def undo(*, organization, actor, counts, source=SOURCE, target=TARGET, group=GROUP) -> None:
    Enrollment = _model("Enrollment")
    rows = applied_batches(organization, source, target)
    if not rows:
        counts["undo_already_done"] += 1
        return
    for row in rows:
        changes = row.changes or {}
        manifest = changes.get("manifest") or {}
        if _post_split_data(str(target), row.created_at, manifest):
            counts["undo_blocked_post_split_data"] += 1
            continue
        _restore_lessons(organization, manifest, counts)
        dropped = manifest.get("source_enrollments_dropped", [])
        counts["undo_sources_reenrolled"] += Enrollment.objects.filter(pk__in=dropped, status="dropped").update(
            status="enrolled", updated_at=timezone.now()
        )
        _drop_target(manifest, counts)
        recompute_absences(list(Enrollment.objects.filter(pk__in=dropped)))
        counts["undo_splits"] += 1
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            new_values={"target": str(target), "source": str(source), "group": str(group), "undo": True},
            reason=UNDO_REASON,
            resource_type=RESOURCE,
            resource_id=row.resource_id,
        )


__all__ = ["UNDO_REASON", "undo"]
