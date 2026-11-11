"""Dublikat jurnal birləşməsinin geri qaytarılması (``merge_duplicate_subjects_20261111 --undo --batch <id>``).

YALNIZ audit manifestindəkini geri qaytarır (W-nin heç bir sətri silinməmişdi — o, sadəcə yenidən aktiv olur).
Birləşmədən SONRA T-də yeni data yaranıbsa (müəllimin dərsi / xanası / balı / yekun nəticəsi, kopyalanmış xananın
dəyişməsi) cütə TOXUNULMUR — ``undo_blocked_post_merge_data`` (müəllimin yazdığı silinməsin). Boş əkiz birləşməsi
mövcud :func:`.twin_merge_restore.restore_empty_merge` ilə qaytarılır.
"""

from __future__ import annotations

from decimal import Decimal

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .duplicate_journal_merge_2026_11_11 import KIND, RESOURCE
from .twin_merge_empty import exam_through
from .twin_merge_restore import restore_empty_merge
from .twin_relocate import recompute_absences

UNDO_KIND = "duplicate_journal_merge_undo"
UNDO_REASON = "Sahib 2026-11-11: dublikat jurnal birləşməsinin geri qaytarılması"
_AFTER_MODELS = ("ComponentScore", "FinalGrade", "CourseWork", "ResitRecord", "CriterionScore")


def _model(name, app="registrar"):
    return django_apps.get_model(app, name)


def _post_merge_data(target_id, since, manifest) -> bool:
    Lesson, LessonMark = _model("Lesson"), _model("LessonMark")
    copied = set(manifest.get("marks_created", []))
    if Lesson.objects.filter(offering_id=target_id, created_at__gt=since).exists():
        return True
    later = LessonMark.objects.filter(lesson__offering_id=target_id, created_at__gt=since)
    if any(str(pk) not in copied for pk in later.values_list("pk", flat=True)):
        return True
    if LessonMark.objects.filter(pk__in=copied, updated_at__gt=since).exists():
        return True
    scores = set(manifest.get("scores_created", []))
    for name in _AFTER_MODELS:
        rows = _model(name).objects.filter(enrollment__offering_id=target_id, created_at__gt=since)
        if any(str(pk) not in scores for pk in rows.values_list("pk", flat=True)):
            return True
    touched = scores | {row[0] for row in manifest.get("scores_replaced", [])}
    return _model("ComponentScore").objects.filter(pk__in=touched, updated_at__gt=since).exists()


def undo(*, organization, actor, counts, batch) -> set:
    """Qaytarır: geri qaytarılan cütlərin imtahan bağlarındakı imtahan id-ləri (yenidən sinxron üçün)."""
    exams = set()
    AuditLog = _model("AuditLog", "audit")
    rows = AuditLog.objects.filter(
        organization=organization, resource_type=RESOURCE, changes__kind=KIND, changes__batch=batch
    )
    undone = set(
        AuditLog.objects.filter(
            organization=organization, resource_type=RESOURCE, changes__kind=UNDO_KIND, changes__batch=batch
        ).values_list("resource_id", flat=True)
    )
    for row in rows.order_by("-created_at", "-pk"):
        changes = row.changes or {}
        manifest, source_id, target_id = changes.get("manifest") or {}, changes.get("source"), changes.get("target")
        if row.resource_id in undone:
            counts["undo_already_done"] += 1
            continue
        with transaction.atomic():
            if manifest.get("empty_twin"):
                done = restore_empty_merge(
                    organization=organization, actor=actor, counts=counts, twin_id=source_id, keep_id=target_id
                )
                if not done:
                    counts["undo_empty_twin_not_restored"] += 1
                    continue
            elif _model("CourseOffering").objects.filter(pk=source_id, is_active=True).exists():
                counts["undo_already_done"] += 1
                continue
            elif _model("CourseOffering").objects.filter(pk=source_id, subject__is_archived=True).exists():
                # Mənbə kart ayrıca kataloq paketi ilə arxivlənib — əvvəl o paket geri qaytarılmalıdır, yoxsa
                # arxiv kartın altında AKTİV jurnal yaranardı.
                counts["undo_blocked_source_card_archived"] += 1
                continue
            elif _post_merge_data(target_id, row.created_at, manifest):
                counts["undo_blocked_post_merge_data"] += 1
                continue
            else:
                _undo_pair(counts, manifest, source_id, target_id)
            counts["undo_pairs"] += 1
            exams.update(str(link["exam"]) for link in manifest.get("exam_links") or [])
            log_action(
                AuditAction.UPDATE,
                user=actor,
                organization=organization,
                new_values={"source": source_id, "target": target_id},
                changes={"kind": UNDO_KIND, "batch": batch, "source": source_id, "target": target_id},
                reason=UNDO_REASON,
                resource_type=RESOURCE,
                resource_id=str(source_id),
            )
    return exams


def _undo_shares(manifest, source_id) -> None:
    JournalShare = _model("JournalShare")
    for entry in manifest.get("shares") or []:
        if entry.get("action") != "moved":
            continue
        share = JournalShare.objects.filter(pk=entry["share"]).first()
        if share is None:
            continue
        JournalShare.objects.filter(pk=share.pk).update(offering_id=source_id, updated_at=timezone.now())
        share.enrollments.set(entry.get("old_enrollments") or [])


def _undo_pair(counts, manifest, source_id, target_id) -> None:
    from core.rls import journal_unlock

    Enrollment, Lesson, LessonMark = _model("Enrollment"), _model("Lesson"), _model("LessonMark")
    Score = _model("ComponentScore")
    get = manifest.get
    with journal_unlock():
        counts["undo_scores_deleted"] += Score.objects.filter(pk__in=get("scores_created", [])).delete()[0]
        for pk, score, entered_by, exam_source in get("scores_replaced", []):
            Score.objects.filter(pk=pk).update(
                score=Decimal(score), entered_by_id=entered_by, exam_source=exam_source, updated_at=timezone.now()
            )
            counts["undo_scores_restored"] += 1
    counts["undo_marks_deleted"] += LessonMark.objects.filter(pk__in=get("marks_created", [])).delete()[0]
    with journal_unlock():
        for mark_id, score in get("marks_score_filled", []):  # yalnız hələ də bizim yazdığımız bal silinir
            counts["undo_mark_scores_cleared"] += LessonMark.objects.filter(pk=mark_id, score=Decimal(score)).update(
                score=None, updated_at=timezone.now()
            )
    blank = {"topic": "", "room_id": None, "instructor_id": None, "end_time": None}
    for lesson_id, fields in get("lesson_fields_filled", []):
        Lesson.objects.filter(pk=lesson_id).update(**{name: blank[name] for name in fields if name in blank})
    Enrollment.objects.filter(pk__in=get("qb_fail_set", [])).update(legacy_qb_fail=False)
    counts["undo_lessons_deleted"] += Lesson.objects.filter(
        pk__in=get("lessons_created", []), marks__isnull=True
    ).delete()[0]
    _undo_shares(manifest, source_id)
    counts["undo_enrollments_deleted"] += Enrollment.objects.filter(
        pk__in=get("enrollments_created", []), lesson_marks__isnull=True, component_scores__isnull=True
    ).delete()[0]
    for enrollment_id, superseded in get("enrollments_reactivated", []):
        Enrollment.objects.filter(pk=enrollment_id).update(
            status="dropped", superseded_by_id=superseded or None, updated_at=timezone.now()
        )
    _model("SyllabusShare", "syllabus").objects.filter(pk__in=get("syllabus_shares_created", [])).delete()
    for syllabus_id, offering_id, subject_id in get("syllabi_moved", []):
        _model("Syllabus", "syllabus").objects.filter(pk=syllabus_id, offering_id=target_id).update(
            offering_id=offering_id, subject_id=subject_id, updated_at=timezone.now()
        )
    ScheduleSlot = _model("ScheduleSlot")
    ScheduleSlot.objects.filter(pk__in=get("slots_created", [])).delete()
    ScheduleSlot.all_objects.filter(pk__in=get("slots_soft_deleted", [])).update(is_deleted=False, deleted_at=None)
    through = exam_through()
    for link in get("exam_links", []):
        if link.get("target_added"):
            through.objects.filter(exam_id=link["exam"], courseoffering_id=target_id).delete()
        through.objects.get_or_create(exam_id=link["exam"], courseoffering_id=source_id)
    dropped = [item if isinstance(item, list) else [item, "enrolled"] for item in get("source_enrollments_dropped", [])]
    for enrollment_id, status in dropped:
        Enrollment.objects.filter(pk=enrollment_id, status="dropped").update(status=status, updated_at=timezone.now())
    _model("CourseOffering").objects.filter(pk=source_id).update(is_active=True, updated_at=timezone.now())
    recompute_absences(
        list(Enrollment.objects.filter(pk__in=[enrollment_id for enrollment_id, _status in dropped]))
        + list(Enrollment.objects.filter(offering_id=target_id, status="enrolled"))
    )


__all__ = ["UNDO_KIND", "UNDO_REASON", "undo"]
