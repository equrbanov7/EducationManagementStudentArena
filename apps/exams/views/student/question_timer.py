"""EXAM-P1-04 — "sual göstərildi" siqnalı (server-authoritative per-question timer).

take_exam client-i vaxt-limitli slide açılanda bu endpoint-ə POST edir; server
İLK göstərilmə anını qeyd edir və countdown-un server qalığını qaytarır. Client
countdown-u bu qalıqla üstələyir — deadline artıq brauzer saatına baxmır.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from apps.exams.features import exam_supervision_enabled
from apps.exams.models import ExamAttempt
from apps.exams.services.question_delivery import safe_delivered_question
from apps.exams.services.question_timer import mark_question_seen
from apps.exams.views.shared.tenant import tenant_scoped_exams

from ._helpers import ensure_student_exam_tenant_context
from .access_guard import ensure_active_attempt_access


def _delivered_question_html(request, attempt, answer):
    """Vaxtlı test sualının təhlükəsiz gövdəsini (düzgün cavabsız) render et."""
    if answer.question.answer_mode not in ("single", "multiple") or attempt.exam.exam_type != "test":
        return None
    ordered_question_ids = list(attempt.answers.order_by("id").values_list("question_id", flat=True))
    try:
        number = ordered_question_ids.index(answer.question_id) + 1
    except ValueError:
        number = 1
    return render_to_string(
        "exams/student/partials/_delivered_question_body.html",
        {
            "delivered": safe_delivered_question(answer),
            "question_id": answer.question_id,
            "question_number": number,
            "question_total": len(ordered_question_ids),
        },
        request=request,
    )


@login_required
@require_POST
def question_seen(request, slug, attempt_id):
    ensure_student_exam_tenant_context(request)
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("exam", "exam__organization"),
        id=attempt_id,
        exam__in=tenant_scoped_exams(request),
        exam__slug=slug,
        user=request.user,
    )
    ensure_active_attempt_access(attempt, request.user, request=request)
    # Təhlükəsizlik auditi 2026-10-07: POST yazı yolu ilə eyni pəncərə qaydası — vaxtı
    # (deadline + grace) bitmiş, sweep-in hələ bağlamadığı cəhd burada bağlanır və vaxtlı
    # sualın məzmunu çatdırılmır; nəzarət kilidi altında da (423) məzmun/taymer yoxdur.
    # Müəllimin əl kilidində (dayandırma) saat dondurulur — POST yolu kimi bağlanmır.
    supervision_on = exam_supervision_enabled()
    manual_lock = supervision_on and attempt.supervision_manual_lock and attempt.supervision_status == "locked"
    if not manual_lock:
        attempt.expire_if_write_window_closed()
    if supervision_on:
        attempt.expire_if_resume_window_expired()
    if attempt.is_finished:
        return JsonResponse({"success": False, "error": "attempt_finished"}, status=409)
    if supervision_on and attempt.supervision_status == "locked":
        return JsonResponse({"success": False, "locked": True, "error": "supervision_locked"}, status=423)

    try:
        question_id = int(request.POST.get("question_id") or "")
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "error": "invalid_question"}, status=400)

    # Yalnız bu attempt-ə çatdırılmış sual üçün (başqa imtahanın sualı 404).
    answer = attempt.answers.select_related("question").filter(question_id=question_id).first()
    if answer is None:
        return JsonResponse({"success": False, "error": "question_not_in_attempt"}, status=404)

    info = mark_question_seen(attempt, answer.question)
    if info.get("attempt_finished"):
        return JsonResponse({"success": False, "error": "attempt_finished"}, status=409)
    payload = {"success": True, **info}
    delivered_html = _delivered_question_html(request, attempt, answer)
    if delivered_html is not None:
        payload["html"] = delivered_html
    return JsonResponse(payload)
