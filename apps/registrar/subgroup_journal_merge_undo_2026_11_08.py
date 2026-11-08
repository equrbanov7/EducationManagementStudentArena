"""Alt qrup jurnallarının birləşdirilməsini geri qaytarmaq (``merge_subgroup_journals_20261108 --undo``).

YALNIZ audit manifestindəkini geri qaytarır. Birləşmədən SONRA ana jurnalda yeni data yaranıbsa (müəllimin dərsi /
xanası / balı / yekun nəticəsi, kopyalanmış xananın dəyişməsi) ailəyə TOXUNULMUR — ``undo_blocked_post_merge_data``
(müəllimin yazdığı silinməsin, gizlənməsin). Ardıcıllıq: kopyalanmış bal və xanalar → seminar bağları → yaradılan
dərslər / qeydiyyatlar / komponentlər / alt qruplar → bərpa olunan qeydiyyatlar əvvəlki vəziyyətə → slotlar → dərs
yükü sətrinə əlavə olunan ana qrup → alt qrup jurnalları və qeydiyyatları yenidən aktiv.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .subgroup_journal_merge_2026_11_08 import REASON, RESOURCE
from .twin_relocate import recompute_absences

UNDO_REASON = "Sahib 2026-11-08: alt qrup jurnallarının birləşdirilməsinin geri qaytarılması"
_AFTER_MODELS = ("ComponentScore", "FinalGrade", "CourseWork", "ResitRecord", "CriterionScore")


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def _changed(rows) -> bool:
    return any((row.updated_at - row.created_at).total_seconds() > 5 for row in rows)


def _post_merge_data(target_id, since, manifest) -> bool:
    """Birləşmədən sonra ana jurnalda müəllimin / başqasının yazdığı data varmı."""
    Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
    copied = set(manifest.get("marks_created", []))
    if Lesson.objects.filter(offering_id=target_id, created_at__gt=since).exists():
        return True
    later = LessonMark.objects.filter(lesson__offering_id=target_id, created_at__gt=since)
    if any(str(pk) not in copied for pk in later.values_list("pk", flat=True)):
        return True
    if _changed(LessonMark.objects.filter(pk__in=copied)):
        return True
    scores = set(manifest.get("scores_created", []))
    for name in _AFTER_MODELS:
        rows = _model(name).objects.filter(enrollment__offering_id=target_id, created_at__gt=since)
        if any(str(pk) not in scores for pk in rows.values_list("pk", flat=True)):
            return True
    return _changed(_model("ComponentScore").objects.filter(pk__in=scores))


def undo(*, organization, actor, counts) -> None:
    AuditLog = _model("AuditLog", "audit")
    rows = AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, reason=REASON)
    for row in rows.order_by("-created_at"):
        manifest = (row.changes or {}).get("manifest") or {}
        target_id = (row.changes or {}).get("target")
        retired = manifest.get("sources_retired") or []
        if not retired:
            continue
        if _model("CourseOffering").objects.filter(pk__in=retired, is_active=True).exists():
            counts["undo_already_done"] += 1
            continue
        if _post_merge_data(target_id, row.created_at, manifest):
            counts["undo_blocked_post_merge_data"] += 1
            continue
        with transaction.atomic():
            _undo_family(organization, actor, counts, manifest, target_id)


def _undo_family(organization, actor, counts, manifest, target_id) -> None:
    Enrollment, Lesson, LessonMark = _model("Enrollment"), _model("Lesson"), _model("LessonMark")
    get = manifest.get
    counts["undo_scores_deleted"] += (
        _model("ComponentScore").objects.filter(pk__in=get("scores_created", [])).delete()[0]
    )
    counts["undo_marks_deleted"] += LessonMark.objects.filter(pk__in=get("marks_created", [])).delete()[0]
    Lesson.objects.filter(pk__in=get("seminar_lessons_tagged", [])).update(seminar_group=None)
    counts["undo_lessons_deleted"] += Lesson.objects.filter(
        pk__in=get("lessons_created", []), marks__isnull=True
    ).delete()[0]
    _model("AssessmentComponent").objects.filter(pk__in=get("components_created", []), scores__isnull=True).delete()
    Enrollment.objects.filter(pk__in=get("seminar_group_set", [])).update(seminar_group=None)
    counts["undo_enrollments_deleted"] += Enrollment.objects.filter(
        pk__in=get("enrollments_created", []), lesson_marks__isnull=True
    ).delete()[0]
    for enrollment_id, superseded in get("enrollments_reactivated", []):
        Enrollment.objects.filter(pk=enrollment_id).update(
            status="dropped", superseded_by_id=superseded or None, updated_at=timezone.now()
        )
    _model("SeminarGroup").objects.filter(pk__in=get("seminar_groups_created", [])).delete()
    _model("SyllabusShare", "syllabus").objects.filter(pk__in=get("syllabus_shares_created", [])).delete()
    ScheduleSlot = _model("ScheduleSlot")
    ScheduleSlot.objects.filter(pk__in=get("slots_created", [])).delete()
    ScheduleSlot.all_objects.filter(pk__in=get("slots_soft_deleted", [])).update(is_deleted=False, deleted_at=None)
    for load_row in _model("TeachingTaskRow", "workload").objects.filter(pk__in=get("load_rows_group_added", [])):
        load_row.groups.remove(target_id)
    Enrollment.objects.filter(pk__in=get("source_enrollments_dropped", []), status="dropped").update(
        status="enrolled", updated_at=timezone.now()
    )
    CourseOffering = _model("CourseOffering")
    CourseOffering.objects.filter(pk__in=get("sources_retired", [])).update(is_active=True)
    CourseOffering.objects.filter(pk__in=get("target_created", []), enrollments__isnull=True).update(is_active=False)
    recompute_absences(
        list(Enrollment.objects.filter(pk__in=get("source_enrollments_dropped", [])))
        + list(Enrollment.objects.filter(offering_id=target_id, status="enrolled"))
    )
    counts["undo_families"] += 1
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        new_values={"target": target_id, "sources": get("sources_retired", [])},
        reason=UNDO_REASON,
        resource_type=RESOURCE,
        resource_id=str(target_id),
    )


__all__ = ["UNDO_REASON", "undo"]
