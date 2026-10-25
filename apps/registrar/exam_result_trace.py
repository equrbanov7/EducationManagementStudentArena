"""Yekun imtahan balının (``FinalGrade.exam_score``) bir imtahan cəhdinə aid olub-olmadığı — registrar tərəfi.

Sahib 2026-10-25: «Şirməmməd üçün olan son imtahan nəticəsini də sil, onunla bağlı olanı, o səhvən olub. Onu əsas
götürmə». ``FinalGrade``-in imtahan cəhdinə bağlantısı YOXDUR (``exam_bridge.record_exam_result`` yalnız balı yazır),
ona görə izi körpünün ÖZ qaydası ilə yoxlayırıq: tələbənin fənn üzrə qeydiyyatı (``resolve_enrollment``) + cəhdin
faizindən körpünün yazacağı bal (``scale_percent`` × ``exam_score_max``) — jurnaldakı bal ona BƏRABƏRDİRSƏ iz bu cəhdindir.

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
from apps.registrar.models import AssessmentScheme, FinalGrade

#: Silinmədən sonra jurnal audit izinə yazılan mənbə qeydi.
CLEAR_SOURCE_NOTE = "imtahan mərkəzi · səhv cəhd silindi"


def final_exam_trace(*, student, subject_id, organization, score_percent, is_expelled=False, attempt=None) -> dict:
    """→ ``{"enrollment": bool, "retake": bool, "current", "expected", "matches": bool}`` (heç nə yazmır)."""
    trace = {"enrollment": False, "retake": False, "current": None, "expected": None, "matches": False}
    if attempt is not None and retake_results.application_for_attempt(
        student=student, subject_id=subject_id, organization=organization, attempt=attempt
    ):
        trace["retake"] = True
        return trace
    enrollment = resolve_enrollment(student=student, subject_id=subject_id, organization=organization)
    if enrollment is None:
        return trace
    trace["enrollment"] = True
    scheme = AssessmentScheme.objects.filter(offering_id=enrollment.offering_id).first()
    grade = FinalGrade.objects.filter(enrollment=enrollment).only("exam_score").first()
    current = getattr(grade, "exam_score", None)
    trace["current"] = current
    if scheme is None or score_percent is None:
        return trace
    expected = 0 if is_expelled else scale_percent(score_percent, finals.exam_score_max(scheme))
    trace["expected"] = expected
    trace["matches"] = current is not None and Decimal(current) == Decimal(expected)
    return trace


def clear_exam_result(*, student, subject_id, organization, expected_score) -> bool:
    """Jurnaldakı yekun imtahan balı hələ ``expected_score``-dursa boşalt (sistem aktoru). → boşaldıldımı."""
    enrollment = resolve_enrollment(student=student, subject_id=subject_id, organization=organization)
    if enrollment is None or expected_score is None:
        return False
    current = FinalGrade.objects.filter(enrollment=enrollment).values_list("exam_score", flat=True).first()
    if current is None or Decimal(current) != Decimal(expected_score):
        return False
    grade = finals.set_exam_score(enrollment=enrollment, score=None, by_user=None, source_note=CLEAR_SOURCE_NOTE)
    return grade is not None and grade.exam_score is None


__all__ = ["CLEAR_SOURCE_NOTE", "clear_exam_result", "final_exam_trace"]
