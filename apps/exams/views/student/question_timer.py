"""EXAM-P1-04 — "sual göstərildi" siqnalı (server-authoritative per-question timer).

take_exam client-i vaxt-limitli slide açılanda bu endpoint-ə POST edir; server
İLK göstərilmə anını qeyd edir və countdown-un server qalığını qaytarır. Client
countdown-u bu qalıqla üstələyir — deadline artıq brauzer saatına baxmır.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from apps.exams.models import ExamAttempt
from apps.exams.services.question_timer import mark_question_seen
from apps.exams.views.shared.tenant import tenant_scoped_exams

from ._helpers import ensure_student_exam_tenant_context
from .access_guard import ensure_active_attempt_access


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
    ensure_active_attempt_access(attempt, request.user)
    if attempt.is_finished:
        return JsonResponse({"success": False, "error": "attempt_finished"}, status=409)

    try:
        question_id = int(request.POST.get("question_id") or "")
    except (TypeError, ValueError):
        return JsonResponse({"success": False, "error": "invalid_question"}, status=400)

    # Yalnız bu attempt-ə çatdırılmış sual üçün (başqa imtahanın sualı 404).
    answer = attempt.answers.select_related("question").filter(question_id=question_id).first()
    if answer is None:
        return JsonResponse({"success": False, "error": "question_not_in_attempt"}, status=404)

    info = mark_question_seen(attempt, answer.question)
    return JsonResponse({"success": True, **info})
