"""Yekun imtahan balının (``FinalGrade.exam_score``) bir imtahan cəhdinə aid olub-olmadığı — registrar tərəfi.

Sahib 2026-10-25: «Şirməmməd üçün olan son imtahan nəticəsini də sil, onunla bağlı olanı, o səhvən olub. Onu əsas
götürmə». ``FinalGrade``-in imtahan cəhdinə bağlantısı YOXDUR (``exam_bridge.record_exam_result`` yalnız balı yazır),
ona görə izi körpünün ÖZ qaydası ilə yoxlayırıq: tələbənin fənn üzrə qeydiyyatı (``resolve_enrollment``) + cəhdin
faizindən körpünün yazacağı bal (``scale_percent`` × ``exam_score_max``). Bal bərabərliyi ilə yanaşı,
sonrakı rəsmi əl qeydi də olmamalıdır (körpünün mənbə üstünlüyü qaydası).

Bu modul exams tərəfinə (``apps.registrar.public`` fasadı ilə, ``purge_exam_attempt`` əmri) iki şey verir:

* :func:`final_exam_trace` — YAZISIZ oxu (dry-run da işlədir; sxem yaradılmır);
* :func:`clear_exam_result` — iz HƏLƏ də bu cəhdindirsə balı ``finals.set_exam_score(None)`` ilə boşaldır
  (mövcud yol: qiymət audit izi + təkrar imtahan qiymətləndirməsi). Bal sonradan dəyişibsə (əl ilə daxiletmə,
  başqa cəhd) — toxunulmur.

25% cəhdi (``retake_results.application_for_attempt``) ``FinalGrade``-ə yazılmır (``ResitRecord``-a gedir) — iz yoxdur.
"""

from __future__ import annotations

from decimal import Decimal

from apps.registrar import finals, retake_results
from apps.registrar.exam_bridge import resolve_enrollment, scale_percent
from apps.registrar.exam_score_precedence import has_later_authoritative_entry
from apps.registrar.exam_score_purge_provenance import capture_purge_provenance, record_purge_provenance
from apps.registrar.models import (
    AssessmentComponent,
    AssessmentScheme,
    ComponentScore,
    CourseOffering,
    Enrollment,
    FinalGrade,
)

#: Silinmədən sonra jurnal audit izinə yazılan mənbə qeydi.
CLEAR_SOURCE_NOTE = "imtahan mərkəzi · səhv cəhd silindi"


def final_exam_trace(
    *,
    student,
    subject_id,
    organization,
    score_percent,
    is_expelled=False,
    attempt=None,
    offering_ids=(),
    lock_enrollment=False,
) -> dict:
    """→ ``{"enrollment": bool, "retake": bool, "current", "expected", "matches": bool}`` (heç nə yazmır).

    ``offering_ids`` — imtahanın bağlı jurnalları (körpü ilə EYNİ qeydiyyat).
    Tətbiq tranzaksiyası ``lock_enrollment=True`` ilə manual bal yazıçısının
    eyni kilidini silinmə/bərpa bitənə qədər saxlayır; dry-run kilid almır."""
    trace = {"enrollment": False, "retake": False, "current": None, "expected": None, "matches": False}
    if attempt is not None and retake_results.application_for_attempt(
        student=student, subject_id=subject_id, organization=organization, attempt=attempt
    ):
        trace["retake"] = True
        return trace
    enrollment = resolve_enrollment(
        student=student, subject_id=subject_id, organization=organization, offering_ids=offering_ids
    )
    if enrollment is None:
        return trace
    if lock_enrollment:
        Enrollment.objects.select_for_update().get(pk=enrollment.pk, organization_id=organization.pk)
    trace["enrollment"] = True
    scheme = AssessmentScheme.objects.filter(offering_id=enrollment.offering_id).first()
    grade = FinalGrade.objects.filter(enrollment=enrollment).only("exam_score").first()
    current = getattr(grade, "exam_score", None)
    trace["current"] = current
    if scheme is None or score_percent is None:
        return trace
    expected = 0 if is_expelled else scale_percent(score_percent, finals.exam_score_max(scheme))
    trace["expected"] = expected
    if has_later_authoritative_entry(enrollment, attempt):
        return trace  # eyni rəqəmli rəsmi əl düzəlişi bu cəhdin izi deyil
    trace["matches"] = current is not None and Decimal(current) == Decimal(expected)
    return trace


def clear_exam_result(
    *, student, subject_id, organization, expected_score, offering_ids=(), expected_enrollment_id=None
) -> bool:
    """Jurnaldakı yekun imtahan balı hələ ``expected_score``-dursa boşalt (sistem aktoru). → boşaldıldımı."""
    enrollment = resolve_enrollment(
        student=student, subject_id=subject_id, organization=organization, offering_ids=offering_ids
    )
    if enrollment is None or expected_score is None:
        return False
    if expected_enrollment_id is not None and enrollment.pk != expected_enrollment_id:
        return False
    current = FinalGrade.objects.filter(enrollment=enrollment).values_list("exam_score", flat=True).first()
    if current is None or Decimal(current) != Decimal(expected_score):
        return False
    grade = finals.set_exam_score(enrollment=enrollment, score=None, by_user=None, source_note=CLEAR_SOURCE_NOTE)
    return grade is not None and grade.exam_score is None


def manual_restore_required(*, enrollment_id, attempt, source_attempt):
    """Əvvəlki cəhddən üstün rəsmi əl qeydi varsa avtomatik silib/bərpa etmə."""
    enrollment = Enrollment.objects.select_related("offering").get(
        pk=enrollment_id, organization_id=attempt.exam.organization_id, student_id=attempt.user_id
    )
    return has_later_authoritative_entry(enrollment, source_attempt, purged_attempt=attempt)


def midterm_restore_required(*, rows, source_finished_at_by_enrollment, organization, lock_journal=False):
    """Silinəcək midterm xanasının əvvəlki mənbəyi rəsmi əl qeydini əzməməlidir."""
    from .midterm_bridge import _overridden

    if not rows:
        return False
    offerings = CourseOffering.objects.filter(
        organization=organization, pk__in={row["component__offering_id"] for row in rows}
    )
    components = AssessmentComponent.objects.filter(
        organization=organization, pk__in={row["component_id"] for row in rows}
    )
    enrollments = Enrollment.objects.filter(organization=organization, pk__in={row["enrollment_id"] for row in rows})
    scores = ComponentScore.objects.filter(organization=organization, pk__in=[row["pk"] for row in rows])
    if lock_journal:
        # Yazıçının eyni sıra/kilidləri: açılış → komponent → qeydiyyat → xana.
        list(offerings.select_for_update().order_by("pk"))
        components = components.select_for_update().order_by("pk")
        enrollments = enrollments.select_for_update().order_by("pk")
        scores = scores.select_for_update().order_by("pk")
    components = {component.pk: component for component in components}
    enrollments = {enrollment.pk: enrollment for enrollment in enrollments}
    scores = {score.pk: score for score in scores}
    for row in rows:
        component = components.get(row["component_id"])
        enrollment = enrollments.get(row["enrollment_id"])
        score = scores.get(row["pk"])
        if component is None or enrollment is None or score is None:
            return True
        if _overridden(component, enrollment, source_finished_at_by_enrollment.get(enrollment.pk), score):
            return True
    return False


__all__ = [
    "CLEAR_SOURCE_NOTE",
    "capture_purge_provenance",
    "clear_exam_result",
    "final_exam_trace",
    "manual_restore_required",
    "midterm_restore_required",
    "record_purge_provenance",
]
