"""``split_share_journal_20261112 --undo`` — payın ayrıca jurnala çıxarılmasını geri qaytarmaq (YALNIZ audit manifesti).

Bölgüdən SONRA yeni jurnalda müəllimin yazdığı data varsa (yeni dərs / xana / bal, kopyalanmış xananın və ya balın
dəyişməsi) geri qaytarılmır — ``undo_blocked_post_split_data`` (müəllimin yazdığı itməsin). Ardıcıllıq: mənbədə
silinmiş dərslər EYNİ id ilə xanaları ilə bərpa → mənbə qeydiyyatları ``enrolled`` → paylar aktiv → slotlar geri →
yeni jurnalın balları, xanaları, dərsləri, komponentləri, qeydiyyatları, slotları silinir → jurnal və qrup silinir
(istinad qalıbsa passiv olur).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.apps import apps as django_apps
from django.db.models import ProtectedError
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .share_journal_split_2026_11_12 import _LESSON_EXTRA, REASON, RESOURCE
from .twin_merge import _LESSON_FIELDS
from .twin_relocate import recompute_absences

UNDO_REASON = "Sahib 2026-11-12 (MR-000188): payın ayrıca jurnala çıxarılmasının geri qaytarılması"
_AFTER_MODELS = ("FinalGrade", "CourseWork", "ResitRecord", "CriterionScore")
_DATES = {"date"}
_TIMES = {"start_time", "end_time"}


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


def _value(name, raw):
    if raw is None:
        return None
    if name in _DATES:
        return dt.date.fromisoformat(raw)
    if name in _TIMES:
        return dt.time.fromisoformat(raw)
    return raw


def _restore_lessons(organization, manifest, counts) -> None:
    Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
    for snap in manifest.get("source_lessons_deleted", []):
        if Lesson.objects.filter(pk=snap["id"]).exists():
            counts["undo_lessons_already_present"] += 1
            continue
        fields = {name: _value(name, snap.get(name)) for name in (*_LESSON_FIELDS, *_LESSON_EXTRA)}
        Lesson.objects.create(id=snap["id"], organization=organization, offering_id=snap["offering_id"], **fields)
        Lesson.objects.filter(pk=snap["id"]).update(created_at=dt.datetime.fromisoformat(snap["created_at"]))
        counts["undo_source_lessons_restored"] += 1
        for cell in snap.get("marks", []):
            LessonMark.objects.create(
                id=cell["id"],
                organization=organization,
                lesson_id=snap["id"],
                enrollment_id=cell["enrollment_id"],
                status=cell["status"],
                score=Decimal(cell["score"]) if cell.get("score") is not None else None,
                entered_by_id=cell.get("entered_by_id"),
            )
            # INSERT-dən dərhal sonra — ``trg_journal_mark_guard`` pəncərəsi keçir (``copy_mark`` kimi).
            LessonMark.objects.filter(pk=cell["id"]).update(created_at=dt.datetime.fromisoformat(cell["created_at"]))
            counts["undo_source_marks_restored"] += 1


def _drop_target(manifest, target_id, counts) -> None:
    get = manifest.get
    counts["undo_scores_deleted"] += (
        _model("ComponentScore").objects.filter(pk__in=get("scores_created", [])).delete()[0]
    )
    counts["undo_marks_deleted"] += _model("LessonMark").objects.filter(pk__in=get("marks_created", [])).delete()[0]
    counts["undo_lessons_deleted"] += _model("Lesson").objects.filter(pk__in=get("lessons_created", [])).delete()[0]
    Slot = _model("ScheduleSlot")
    Slot.all_objects.filter(pk__in=get("slots_created", [])).delete()
    Slot.all_objects.filter(pk__in=get("slots_soft_deleted", [])).update(
        is_deleted=False, deleted_at=None, updated_at=timezone.now()
    )
    Offering, OrgUnit = _model("CourseOffering"), _model("OrgUnit", "organizations")
    try:
        Offering.objects.filter(pk=target_id).delete()
        OrgUnit.objects.filter(pk__in=get("group_created", [])).delete()
        counts["undo_journals_deleted"] += 1
    except ProtectedError:
        _model("Enrollment").objects.filter(offering_id=target_id, status="enrolled").update(
            status="dropped", updated_at=timezone.now()
        )
        Offering.objects.filter(pk=target_id).update(is_active=False, updated_at=timezone.now())
        OrgUnit.objects.filter(pk__in=get("group_created", [])).update(is_active=False, updated_at=timezone.now())
        counts["undo_journals_deactivated"] += 1


def undo(*, organization, actor, counts) -> None:
    AuditLog = _model("AuditLog", "audit")
    Offering, Enrollment = _model("CourseOffering"), _model("Enrollment")
    rows = AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, reason=REASON)
    for row in rows.order_by("-created_at"):
        changes = row.changes or {}
        manifest, target_id = changes.get("manifest") or {}, changes.get("target")
        if not target_id or not Offering.objects.filter(pk=target_id, is_active=True).exists():
            counts["undo_already_done"] += 1
            continue
        if _post_split_data(target_id, row.created_at, manifest):
            counts["undo_blocked_post_split_data"] += 1
            continue
        _restore_lessons(organization, manifest, counts)
        dropped = manifest.get("source_enrollments_dropped", [])
        counts["undo_sources_reenrolled"] += Enrollment.objects.filter(pk__in=dropped, status="dropped").update(
            status="enrolled", updated_at=timezone.now()
        )
        counts["undo_shares_reactivated"] += (
            _model("JournalShare")
            .objects.filter(pk__in=manifest.get("shares_retired", []), is_active=False)
            .update(is_active=True, updated_at=timezone.now())
        )
        _drop_target(manifest, target_id, counts)
        recompute_absences(list(Enrollment.objects.filter(pk__in=dropped)))
        source = Offering.objects.filter(pk=changes.get("source")).first()
        if source is not None:
            from .journal_shares import forget

            forget(source)
        counts["undo_splits"] += 1
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            new_values={"target": target_id, "source": changes.get("source"), "undo": True},
            reason=UNDO_REASON,
            resource_type=RESOURCE,
            resource_id=row.resource_id,
        )


__all__ = ["UNDO_REASON", "undo"]
