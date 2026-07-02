"""
assignments/views/student.py
──────────────────────────
Student-facing views for assignments.

Contains:
- assignment_detail
- submit_assignment
- my_submissions
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from apps.assignments.services import create_assignment_submission
from apps.task_submission_core.public import annotate_student_review_state, prepare_submission_upload
from core.helpers import REVIEW_EDIT_LOCK_WINDOW

from ..shared._helpers import _append_return_to, _assignment_back_url, _get_tenant_assignment_or_404, _student_return_to

logger = logging.getLogger(__name__)

REVIEW_WINDOW_MINUTES = int(REVIEW_EDIT_LOCK_WINDOW.total_seconds() // 60)


def _annotate_review_state(submissions):
    return annotate_student_review_state(submissions)


# ════════════════════════════════════════════════════════════════════════════
# Assignment Detail (Student)
# ════════════════════════════════════════════════════════════════════════════


@login_required
def assignment_detail(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işinin detalları (tələbə üçün)                                     │
    │ GET /assignments/<pk>/                                                     │
    │                                                                         │
    │ Tələbə burada:                                                          │
    │ - Assignment məlumatlarını görür                                           │
    │ - Əvvəlki cavablarını görür                                             │
    │ - Yeni cavab göndərə bilir (cəhd varsa)                                 │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    assignment = _get_tenant_assignment_or_404(request, pk)

    # ─────────────────────────────────────────────────────────────────────────
    # İcazə yoxlaması - tələbə yalnız özünə təyin olunmuşlara baxa bilər
    # ─────────────────────────────────────────────────────────────────────────
    if getattr(request.user, "is_student", False):
        has_access = assignment.assigned_students.filter(id=request.user.id).exists()
        if not has_access:
            messages.error(request, pgettext("assignments.views.message", "no_assignment_access"))
            return redirect("courses:course_dashboard", course_id=assignment.course.id)

    # İstifadəçinin əvvəlki cavablarını al
    user_submissions = _annotate_review_state(
        assignment.submissions.filter(user=request.user).order_by("-submitted_at")
    )
    user_attempts = len(user_submissions)
    return_to_url = _student_return_to(request)

    context = {
        "assignment": assignment,
        "user_submissions": user_submissions,
        "user_attempts": user_attempts,
        "can_submit": assignment.can_user_submit(request.user),
        "attempts_left": assignment.max_attempts - user_attempts,
        "back_url": _assignment_back_url(request, assignment),
        "results_url": _append_return_to(
            f"/assignments/{assignment.id}/my-submissions/",
            return_to_url,
        ),
        "review_window_minutes": REVIEW_WINDOW_MINUTES,
    }

    return render(request, "assignments/assignment_detail.html", context)


# ════════════════════════════════════════════════════════════════════════════
# Submit Assignment
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["POST"])
def submit_assignment(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işinə cavab göndərmək                                              │
    │ POST /assignments/<pk>/submit/                                             │
    │                                                                         │
    │ Form data: content (text), file (optional)                              │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    assignment = _get_tenant_assignment_or_404(request, pk)

    if not assignment.assigned_students.filter(id=request.user.id).exists():
        return JsonResponse(
            {
                "success": False,
                "error": pgettext("assignments.views.message", "no_assignment_access"),
            },
            status=403,
        )

    # Cavab göndərə bilərmi yoxla
    if not assignment.can_user_submit(request.user):
        return JsonResponse(
            {
                "success": False,
                "error": pgettext("assignments.views.message", "submit_not_allowed"),
            },
            status=400,
        )

    uploaded_file = request.FILES.get("file")
    original_file_name = ""
    if uploaded_file is not None:
        try:
            original_file_name = prepare_submission_upload(uploaded_file)
        except ValidationError as exc:
            return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)

    try:
        submission = create_assignment_submission(
            assignment,
            request.user,
            submission_file=uploaded_file,
            submission_text=request.POST.get("content", ""),
            original_file_name=original_file_name,
            attempt_number=assignment.get_user_attempts(request.user) + 1,
        )

        messages.success(request, pgettext("assignment.message", "submission_sent_successfully"))
        return JsonResponse(
            {
                "success": True,
                "message": pgettext("assignment.message", "submission_sent_successfully"),
                "submission_id": submission.id,
            }
        )

    except Exception:
        logger.exception("Unexpected error in submit_assignment")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)


# ════════════════════════════════════════════════════════════════════════════
# My Submissions
# ════════════════════════════════════════════════════════════════════════════


@login_required
def my_submissions(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Tələbənin öz cavablarını görmək                                         │
    │ GET /assignments/<pk>/my-submissions/                                      │
    │                                                                         │
    │ Tələbə burada:                                                          │
    │ - Bütün göndərdiyi cavabları görür                                      │
    │ - Qiymətlərini görür                                                    │
    │ - Müəllim rəyini görür                                                  │
    │ - Qalan cəhd sayını görür                                               │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    assignment = _get_tenant_assignment_or_404(request, pk)

    # ─────────────────────────────────────────────────────────────────────────
    # İcazə yoxlaması - yalnız özünə təyin olunmuş assignment-lərə baxa bilər
    # ─────────────────────────────────────────────────────────────────────────
    if not assignment.assigned_students.filter(id=request.user.id).exists():
        messages.error(request, pgettext("assignments.views.message", "no_assignment_access"))
        return redirect("courses:course_dashboard", course_id=assignment.course.id)

    # İstifadəçinin cavablarını al
    submissions = _annotate_review_state(assignment.submissions.filter(user=request.user).order_by("-submitted_at"))
    user_attempts = len(submissions)
    return_to_url = _student_return_to(request)

    context = {
        "assignment": assignment,
        "submissions": submissions,
        "user_attempts": user_attempts,
        "can_submit": assignment.can_user_submit(request.user),
        "attempts_left": assignment.max_attempts - user_attempts,
        "back_url": _assignment_back_url(request, assignment),
        "detail_url": _append_return_to(
            f"/assignments/{assignment.id}/detail/",
            return_to_url,
        ),
        "review_window_minutes": REVIEW_WINDOW_MINUTES,
    }

    return render(request, "assignments/my_submissions.html", context)
