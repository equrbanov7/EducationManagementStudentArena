"""teacher exams paketi — tələbəyə əlavə cəhd (ikinci şans) vermə."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.models import StudentExamAttemptGrant
from apps.exams.services.access_policy import _ensure_teacher

from ._shared import (
    _get_editable_exam_or_404,
    _organization_selection_redirect,
    _resolve_required_organization,
    _safe_same_origin_redirect_path,
)

User = get_user_model()


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


@login_required
@require_POST
def grant_extra_attempt(request, slug):
    """Konkret bir tələbəyə bu imtahan üçün əlavə cəhd verir.

    Qlobal ``max_attempts_per_user`` dəyişmir — yalnız seçilmiş tələbənin
    limiti artır (``Exam.attempts_left_for`` grant-ı nəzərə alır).
    """
    organization = _resolve_required_organization(request)
    if organization is None:
        return _organization_selection_redirect(request)
    _ensure_teacher(request.user)

    exam = _get_editable_exam_or_404(request, slug)

    def _fail(error, status):
        if _is_ajax(request):
            return JsonResponse({"success": False, "error": error}, status=status)
        messages.error(request, error)
        return redirect(_back_url())

    def _back_url():
        return _safe_same_origin_redirect_path(request, request.META.get("HTTP_REFERER")) or reverse(
            "exams:teacher_exam_results", kwargs={"slug": exam.slug}
        )

    raw_student_id = (request.POST.get("student_id") or "").strip()
    if not raw_student_id.isdigit():
        return _fail("invalid_student", 400)

    student = User.objects.filter(id=int(raw_student_id), is_active=True).first()
    if student is None:
        return _fail("student_not_found", 404)

    try:
        extra = int(request.POST.get("extra_attempts", 1))
    except (TypeError, ValueError):
        extra = 1
    extra = max(1, min(extra, 10))

    grant, created = StudentExamAttemptGrant.objects.get_or_create(
        exam=exam,
        student=student,
        defaults={"extra_attempts": extra, "granted_by": request.user},
    )
    if not created:
        # Mövcud grant-a əlavə et (təkrar "ikinci şans" verilə bilər).
        grant.extra_attempts = grant.extra_attempts + extra
        grant.granted_by = request.user
        grant.save(update_fields=["extra_attempts", "granted_by", "updated_at"])

    if _is_ajax(request):
        return JsonResponse(
            {
                "success": True,
                "student_id": student.id,
                "extra_attempts": grant.extra_attempts,
                "attempts_left": exam.attempts_left_for(student),
            }
        )

    messages.success(
        request,
        pgettext("exams.view.exams.message", "extra_attempt_granted"),
    )
    return redirect(_back_url())
