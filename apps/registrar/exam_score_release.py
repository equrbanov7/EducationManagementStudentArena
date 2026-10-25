"""Kağız imtahan nəticəsinin TƏLƏBƏYƏ görünmə gecikməsi (sahib 2026-10-25).

Sahib: «yazılı/praktiki imtahan nəticəsi tələbə kabinetində təsdiqdən 1 gün sonra görünsün». Gecikmə
«Sistem tənzimləmələri» → ``exam.score_release_hours`` (defolt 24; 0 — dərhal).

Qayda: «İmtahan balının daxil edilməsi» ekranında İLK təsdiq (``ExamScoreEntry.kind=initial``) anından
``release_hours`` keçməyibsə həmin imtahanın (midterm və ya final) balı TƏLƏBƏ səthlərində gizlənir —
daxil edənin 15 dəqiqəlik düzəlişləri də bu müddətə düşür. Sonrakı rəsmi dəyişikliklər (apellyasiya,
RİM təqdimatı) ilk təsdiqdən sonra gəldiyi üçün dərhal görünür.

Yalnız TƏLƏBƏ səthləri maskalanır («Fənlərim», öz jurnalı, «Nəticələrim» / «Ümumi tədris məlumatı»,
transkript) — müəllim, İmtahan Mərkəzi, RİM, dekanlıq balı dərhal görür. Maska yaddaşdadır (``FinalsBatch``
nüsxəsi); DB-yə heç nə yazılmır. Sorğu: tələbə başına BİR (``pending_releases``), gecikmə 0-dırsa heç biri.
"""

from __future__ import annotations

import copy
from datetime import timedelta

from django.utils import timezone

from .models import ComponentKind, ExamAssessment, ExamScoreEntry, ExamScoreEntryKind


def release_delay() -> timedelta:
    from core.runtime_settings_exam_scores import release_hours

    return timedelta(hours=release_hours())


def pending_releases(enrollment_ids, *, now=None) -> dict:
    """``{enrollment_id: {assessment: visible_at}}`` — hələ tələbəyə açılmamış kağız nəticələr (BİR sorğu)."""
    ids = [value for value in enrollment_ids if value is not None]
    delay = release_delay()
    if not ids or delay <= timedelta(0):
        return {}
    now = now or timezone.now()
    rows = ExamScoreEntry.objects.filter(
        enrollment_id__in=ids, kind=ExamScoreEntryKind.INITIAL, created_at__gt=now - delay
    ).values_list("enrollment_id", "assessment", "created_at")
    result: dict = {}
    for enrollment_id, assessment, created_at in rows:
        slot = result.setdefault(enrollment_id, {})
        visible_at = created_at + delay
        slot[assessment] = max(slot.get(assessment, visible_at), visible_at)
    return result


def is_pending(pending, enrollment_id, assessment) -> bool:
    return assessment in pending.get(enrollment_id, {})


def visible_at(pending, enrollment_id, assessment):
    return pending.get(enrollment_id, {}).get(assessment)


def is_midterm_component(component) -> bool:
    from .interim_assessment import MIDTERM_COMPONENT_NAME

    return getattr(component, "kind", None) == ComponentKind.KOLLOKVIUM and component.name == MIDTERM_COMPONENT_NAME


def masked_component_scores(component_scores, components, *, hide_midterm: bool) -> list:
    """Midterm gizlidirsə «Midterm» xanasının balı siyahıdan çıxarılır (giriş balı da onsuz hesablanır)."""
    if not hide_midterm:
        return list(component_scores)
    hidden = {c.pk for c in components if is_midterm_component(c)}
    return [score for score in component_scores if score.component_id not in hidden]


def mask_batch(batch, pending) -> None:
    """``FinalsBatch``-i tələbə görünüşü üçün YERİNDƏ maskala (final balı ``None``, midterm xanası yox)."""
    if batch is None or not pending:
        return
    for enrollment_id, assessments in pending.items():
        if ExamAssessment.FINAL in assessments and batch.final_grades is not None:
            grade = batch.final_grades.get(enrollment_id)
            if grade is not None:
                hidden = copy.copy(grade)
                hidden.exam_score = None
                batch.final_grades[enrollment_id] = hidden
        if ExamAssessment.MIDTERM in assessments and batch.scores_by_enrollment is not None:
            scores = batch.scores_by_enrollment.get(enrollment_id)
            if scores:
                midterm_ids = _midterm_component_ids(batch)
                batch.scores_by_enrollment[enrollment_id] = [s for s in scores if s.component_id not in midterm_ids]


def _midterm_component_ids(batch) -> set:
    return {
        component.pk
        for components in (batch.components_by_offering or {}).values()
        for component in components
        if is_midterm_component(component)
    }


def mask_for_student(batch, enrollments) -> dict:
    """Bir addımda: gizli nəticələri tap + ``batch``-i maskala; ``pending`` xəritəsini qaytar (şablon nişanı üçün)."""
    pending = pending_releases([getattr(e, "pk", None) for e in enrollments])
    mask_batch(batch, pending)
    return pending


def student_interim_view(enrollment, kollokviums) -> tuple:
    """Tələbənin öz jurnalı: midterm hələ açılmayıbsa xana boş + «nə vaxt görünəcək», giriş balı midtermsiz.

    Nəticə ``(kollokviums, entry_kwargs)`` — ``entry_kwargs`` ``gradebook_components.entry_parts_for``-a
    ötürülür (gizli deyilsə boş dict, əlavə sorğu yoxdur; gizlidirsə komponent + bal siyahısı, 2 sorğu).
    """
    # Kağız midterm həmişə mənbəli (``exam_source``, ``auto``) yazılır — belə xana yoxdursa sorğu da yoxdur.
    if not any(row.get("auto") and is_midterm_component(row["component"]) for row in kollokviums):
        return kollokviums, {}
    at = visible_at(pending_releases([enrollment.pk]), enrollment.pk, ExamAssessment.MIDTERM)
    if at is None:
        return kollokviums, {}
    from .models import AssessmentComponent, ComponentScore

    rows = [
        {**row, "score": None, "auto": False, "release_at": at} if is_midterm_component(row["component"]) else row
        for row in kollokviums
    ]
    components = list(AssessmentComponent.objects.filter(offering_id=enrollment.offering_id))
    scores = masked_component_scores(
        ComponentScore.objects.filter(enrollment=enrollment), components, hide_midterm=True
    )
    return rows, {"components": components, "component_scores": scores}


__all__ = [
    "student_interim_view",
    "is_midterm_component",
    "is_pending",
    "mask_batch",
    "mask_for_student",
    "masked_component_scores",
    "pending_releases",
    "release_delay",
    "visible_at",
]
