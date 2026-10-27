"""``merge_level_journals --undo <paket>`` — səviyyə jurnalı birləşməsini audit manifestinə görə geri qaytarır.

Hər jurnal sətri (``registrar.level_merge``, ``<paket>:<legacy jurnal>``) üçün: söndürülən mənbə payları yenidən aktiv
(həmin açılış × müəllim üzrə başqa aktiv pay yoxdursa), evdəki paya əlavə olunan sətirlər çıxarılır, köçən xanalar
mənbə qeydiyyatın KÖHNƏ dərsinə yeni sətir kimi qaytarılır (``created_at`` saxlanılır; mənbədə həmin dərsdə xana
varsa toxunulmur), mənbə qeydiyyat ƏVVƏL bərpa olunur (``guest_merge.restore_source``), paketin yaratdığı ev
qeydiyyatı heç bir datası qalmayıbsa («Jurnal təmizliyi» sübut süzgəci) silinir, qalıbsa ``dropped`` olur (sayılır). Heç bir xana silinmir — yalnız yerinə qayıdır.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.db import transaction

from . import guest_merge, journal_hygiene
from .level_merge import BATCH_RESOURCE, REASON
from .models import Enrollment, JournalShare, Lesson, LessonMark
from .twin_relocate import copy_mark, recompute_absences


def undo_batch(organization, batch: str, *, actor) -> Counter:
    audit_model = django_apps.get_model("audit", "AuditLog")
    counts: Counter = Counter()
    entries = audit_model.objects.filter(
        organization=organization, resource_type=BATCH_RESOURCE, resource_id__startswith=f"{batch}:"
    ).order_by("-created_at")
    for entry in entries:
        counts["journals_in_batch"] += 1
        with transaction.atomic():
            _undo_journal(entry.new_values or {}, actor=actor, counts=counts)
    return counts


def _undo_journal(manifest: dict, *, actor, counts: Counter) -> None:
    for share in JournalShare.objects.filter(pk__in=manifest.get("shares_deactivated") or [], is_active=False):
        if JournalShare.objects.filter(
            offering_id=share.offering_id, teacher_id=share.teacher_id, is_active=True
        ).exists():
            counts["reactivate_conflict"] += 1
            continue
        share.is_active = True
        share.save(update_fields=["is_active", "updated_at"])
        counts["shares_reactivated"] += 1
    for share_id, added in (manifest.get("share_added") or {}).items():
        share = JournalShare.objects.filter(pk=share_id).first()
        if share is not None:
            share.enrollments.remove(*added)
            counts["share_rows_removed"] += len(added)
    for row in reversed(manifest.get("students") or []):
        _undo_student(row, actor=actor, counts=counts)


def _undo_student(row: dict, *, actor, counts: Counter) -> None:
    source = Enrollment.objects.select_for_update(of=("self",)).filter(pk=row.get("source")).first()
    host = Enrollment.objects.select_for_update(of=("self",)).filter(pk=row.get("host_enrollment")).first()
    if source is None or host is None:
        counts["student_rows_missing"] += 1
        return
    counts["sources_restored"] += guest_merge.restore_source(target=host, by_user=actor, reason=f"undo — {REASON}")
    lessons = {str(lesson.pk): lesson for lesson in Lesson.objects.filter(pk__in=[old for _new, old in row["marks"]])}
    taken = {str(pk) for pk in LessonMark.objects.filter(enrollment=source).values_list("lesson_id", flat=True)}
    for new_id, old_lesson in row.get("marks") or []:
        mark = LessonMark.objects.select_for_update(of=("self",)).filter(pk=new_id, enrollment=host).first()
        lesson = lessons.get(str(old_lesson))
        if mark is None or lesson is None:
            counts["mark_missing"] += 1
            continue
        if str(lesson.pk) in taken:
            counts["mark_source_cell_filled_kept"] += 1
            continue
        copy_mark(mark, lesson=lesson, enrollment=source)
        taken.add(str(lesson.pk))
        mark.delete()
        counts["marks_returned"] += 1
    if Enrollment.objects.filter(pk=host.pk).filter(*journal_hygiene.no_evidence_filters()).exists():
        host.delete()
        counts["host_rows_deleted"] += 1
        recompute_absences([source])
        return
    if host.status == Enrollment.Status.ENROLLED:
        host.status = Enrollment.Status.DROPPED
        host.save(update_fields=["status", "updated_at"])
    counts["host_rows_dropped_has_data"] += 1
    recompute_absences([source, host])


__all__ = ["undo_batch"]
