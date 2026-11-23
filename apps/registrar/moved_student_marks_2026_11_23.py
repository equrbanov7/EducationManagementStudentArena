"""MR-000706 / MR-000710 (2026-11-23): Uluxanova Tahirə — 505/6 G jurnalındakı qeydlər 505/6 MB jurnalına (``copy_moved_student_marks_20261123``).

Müəllim Reyhan Əhmədova: tələbə 505/6 MB-dədir, «Ali məktəb pedaqogikası» MB jurnalında olmalıdır (MR-000706 — G
jurnalından çıxarılıb MB jurnalına yazıldı). Sonra: «Bəs tələbənin iştirak məlumatlarını hardan alım? Yeni jurnala
köçməyib» (MR-000710). G-dəki qeydiyyat ``dropped``-dur, xanaları və İmtahan Mərkəzinin yazdığı Midterm balı (30)
orada qalıb. Hər iki jurnalın müəllimi eynidir, dərslər eyni günlərdədir.

Qayda («yalnız boşluğu doldur», sabit id-lər):

* mənbə — G açılışında tələbənin ``dropped`` qeydiyyatı; hədəf — MB açılışında ``enrolled`` qeydiyyatı (hər biri tək);
* hər mənbə xanası üçün hədəfdə EYNİ tarix + növ üzrə TƏK dərs varsa və orada tələbənin xanası yoxdursa — xana
  yaradılır (iştirak / qayıb / bal eyni); qeyri-müəyyən və ya artıq dolu — sayılır, toxunulmur;
* komponent balı (Midterm …): hədəfdə eyni ad + növlü TƏK komponent varsa və balı yoxdursa — kopyalanır
  (``exam_source`` ilə birlikdə);
* hədəfin qayıb saatı yenidən hesablanır. Mənbəyə toxunulmur.

``undo`` — yalnız həmin ``batch``-ın yaratdığı xanaları / balları silir. Stdout-a YALNIZ saylar.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

RESOURCE = "registrar.moved_student_marks_20261123"
REASON = "MR-000710: Uluxanova Tahirə — 505/6 G jurnalındakı davamiyyət və Midterm 505/6 MB jurnalına köçürüldü"
UNDO_REASON = "MR-000710: köçürülmüş xanaların geri götürülməsi"

SOURCE_OFFERING = "321772aa-08b4-42e3-b257-432cda4195ea"  # 505/6 G «Ali məktəb pedaqogikası»
TARGET_OFFERING = "058265ab-2074-4e60-8461-57a291ada6aa"  # 505/6 MB «Ali məktəb pedaqogikası»
STUDENT_ID = 2475  # Uluxanova Tahirə


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def new_batch() -> str:
    return f"mvmarks-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _single(queryset):
    rows = list(queryset[:2])
    return rows[0] if len(rows) == 1 else None


def run(*, organization, actor, counts: Counter, batch: str, source=None, target=None, student_id=None) -> str:
    from .gradebook_marks import recompute_absence_hours_many

    batch = batch or new_batch()
    Enrollment = _model("Enrollment")
    LessonMark = _model("LessonMark")
    Lesson = _model("Lesson")
    ComponentScore = _model("ComponentScore")
    AssessmentComponent = _model("AssessmentComponent")
    source_id, target_id = source or SOURCE_OFFERING, target or TARGET_OFFERING
    student_id = student_id or STUDENT_ID
    src = _single(
        Enrollment.objects.filter(
            organization=organization, offering_id=source_id, student_id=student_id, status=Enrollment.Status.DROPPED
        )
    )
    dst = _single(
        Enrollment.objects.select_for_update(of=("self",)).filter(
            organization=organization, offering_id=target_id, student_id=student_id, status=Enrollment.Status.ENROLLED
        )
    )
    if src is None or dst is None:
        counts["enrollment_not_found"] += 1
        return batch
    created_marks, created_scores = [], []
    for mark in LessonMark.objects.filter(enrollment=src).select_related("lesson"):
        lesson = _single(Lesson.objects.filter(offering_id=target_id, date=mark.lesson.date, kind=mark.lesson.kind))
        if lesson is None:
            counts["mark_no_matching_lesson"] += 1
            continue
        if LessonMark.objects.filter(lesson=lesson, enrollment=dst).exists():
            counts["mark_target_filled"] += 1
            continue
        new = LessonMark.objects.create(
            organization=organization,
            lesson=lesson,
            enrollment=dst,
            status=mark.status,
            score=mark.score,
            entered_by=mark.entered_by,
        )
        created_marks.append(str(new.pk))
    for score in ComponentScore.objects.filter(enrollment=src).select_related("component"):
        component = _single(
            AssessmentComponent.objects.filter(
                offering_id=target_id, name=score.component.name, kind=score.component.kind
            )
        )
        if component is None:
            counts["score_no_matching_component"] += 1
            continue
        if ComponentScore.objects.filter(component=component, enrollment=dst).exists():
            counts["score_target_filled"] += 1
            continue
        new = ComponentScore.objects.create(
            organization=organization,
            component=component,
            enrollment=dst,
            score=score.score,
            entered_by=score.entered_by,
            exam_source=score.exam_source,
        )
        created_scores.append(str(new.pk))
    counts["marks_copied"] += len(created_marks)
    counts["scores_copied"] += len(created_scores)
    if not created_marks and not created_scores:
        counts["nothing_to_copy"] += 1
        return batch
    recompute_absence_hours_many([dst])
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        reason=REASON,
        resource_type=RESOURCE,
        resource_id=str(dst.pk),
        resource_repr="Köçmüş tələbənin xanaları yeni jurnala",
        old_values={"source_enrollment": str(src.pk)},
        new_values={"batch": batch, "marks": created_marks, "scores": created_scores},
    )
    return batch


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    from .gradebook_marks import recompute_absence_hours_many

    AuditLog = _model("AuditLog", "audit")
    Enrollment = _model("Enrollment")
    rows = list(AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, new_values__batch=batch))
    if not rows:
        counts["undo_batch_unknown"] += 1
        return
    for row in rows:
        values = row.new_values or {}
        marks, _ = _model("LessonMark").objects.filter(pk__in=values.get("marks") or []).delete()
        scores, _ = _model("ComponentScore").objects.filter(pk__in=values.get("scores") or []).delete()
        counts["undo_marks_removed"] += marks
        counts["undo_scores_removed"] += scores
        recompute_absence_hours_many(list(Enrollment.objects.filter(pk=row.resource_id)))
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            reason=UNDO_REASON,
            resource_type=f"{RESOURCE}.undo",
            resource_id=row.resource_id,
            resource_repr="Köçürülmüş xanalar geri götürüldü",
            old_values={"batch": batch},
        )


__all__ = ["SOURCE_OFFERING", "STUDENT_ID", "TARGET_OFFERING", "new_batch", "run", "undo"]
