"""results paketi — «Nəticəni ləğv et» / «Ləğvi bərpa et» konteksti (sahib 2026-11-17).

Nəticələr siyahısında köçürmə və s. səbəbinə görə nəticəni ləğv etmək (və səhv olarsa geri qaytarmaq) yalnız
imtahan mərkəzinə açıqdır; sorğu yoxdur (rol yoxlaması + sabit siyahı). POST-lar
``exams:exam_center_attempt_annul`` / ``exam_center_attempt_restore``-a gedir (server hər şeyi yenidən yoxlayır).
"""

from django.utils import timezone

from apps.exams.services.final_center import ANNUL_REASONS, can_manage_final_center


def annul_page_context(request, exam) -> dict:
    if exam.is_deleted or not can_manage_final_center(request.user):
        return {"can_annul_results": False}
    return {
        "can_annul_results": True,
        "annul_reasons": ANNUL_REASONS,
        "annul_today": timezone.localdate().isoformat(),
    }


__all__ = ["annul_page_context"]
