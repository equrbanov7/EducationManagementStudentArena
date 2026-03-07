"""
projects/views/teacher.py
──────────────────────────
Teacher-facing views for projects.

Contains:
- review_submissions
- grade_submission
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from core.helpers import REVIEW_EDIT_LOCK_WINDOW
from core.permissions import request_has_permission

from ._helpers import _get_tenant_project_or_404, _get_tenant_submission_or_404, _teacher_review_back_url


# ════════════════════════════════════════════════════════════════════════════
# Review Submissions
# ════════════════════════════════════════════════════════════════════════════


@login_required
def review_submissions(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Cavabları yoxlamaq (müəllim üçün)                                       │
    │ GET /projects/<pk>/submissions/                                         │
    │                                                                         │
    │ Müəllim burada:                                                         │
    │ - Bütün tələbə cavablarını görür                                        │
    │ - Qiymət verə bilir                                                     │
    │ - Rəy yaza bilir                                                        │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = _get_tenant_project_or_404(request, pk)

    # İcazə yoxlaması
    if not request.user.is_teacher_or_above or project.course.owner != request.user:
        messages.error(request, pgettext("projects.views.message", "permission_denied"))
        return redirect("courses:course_dashboard", course_id=project.course.id)

    submissions = project.submissions.select_related("student").order_by("-submitted_at")
    selected_submission_raw = (request.GET.get("submission") or "").strip()
    selected_submission_id = selected_submission_raw if selected_submission_raw.isdigit() else ""

    context = {
        "project": project,
        "submissions": submissions,
        "selected_submission_id": selected_submission_id,
        "back_url": _teacher_review_back_url(request, project),
    }

    return render(request, "projects/review_submissions.html", context)


# ════════════════════════════════════════════════════════════════════════════
# Grade Submission
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["POST"])
def grade_submission(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Cavabı qiymətləndirmək                                                  │
    │ POST /projects/submission/<pk>/grade/                                   │
    │                                                                         │
    │ Form data: grade, feedback (optional)                                   │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    submission = _get_tenant_submission_or_404(request, pk)

    if not request_has_permission(request, "grade.input"):
        return JsonResponse(
            {"success": False, "error": pgettext("projects.views.message", "permission_denied")},
            status=403,
        )

    # İcazə yoxlaması
    if not request.user.is_teacher_or_above or submission.project.course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("projects.views.message", "permission_denied")},
            status=403,
        )

    if (
        submission.status == "graded"
        and submission.graded_at
        and timezone.now() >= submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
    ):
        return JsonResponse(
            {"success": False, "error": "Yoxlama müddəti bitib. Artıq dəyişiklik etmək mümkün deyil."},
            status=400,
        )

    try:
        submission.grade = request.POST.get("grade")
        submission.feedback = request.POST.get("feedback", "")
        submission.status = "graded"
        if not submission.graded_at:
            submission.graded_at = timezone.now()
        submission.graded_by = request.user
        submission.save()

        messages.success(request, pgettext("projects.views.message", "grade_given"))
        return JsonResponse({"success": True, "message": pgettext("projects.views.message", "grade_given")})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
