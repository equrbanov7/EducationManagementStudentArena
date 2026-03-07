"""
assignments/views/student.py
──────────────────────────
Student-facing views for assignments.

Contains:
- assignment_detail
- submit_assignment
- my_submissions
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from apps.assignments.models import AssignmentSubmission
from core.helpers import REVIEW_EDIT_LOCK_WINDOW
from core.upload_security import randomize_uploaded_filename, validate_uploaded_file

from ._helpers import _append_return_to, _assignment_back_url, _get_tenant_assignment_or_404, _student_return_to


REVIEW_WINDOW_MINUTES = int(REVIEW_EDIT_LOCK_WINDOW.total_seconds() // 60)


def _annotate_review_state(submissions):
    current_time = timezone.now()
    prepared_submissions = []

    for submission in submissions:
        submission.has_grade = submission.grade is not None
        submission.show_review_data = submission.status == "graded" and (
            not submission.graded_at or current_time >= submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
        )
        submission.review_available_in_seconds = 0
        if submission.status == "graded" and submission.graded_at and not submission.show_review_data:
            reveal_at = submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
            submission.review_available_in_seconds = max(0, int((reveal_at - current_time).total_seconds()))
        prepared_submissions.append(submission)

    return prepared_submissions


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
    user_submissions = _annotate_review_state(assignment.submissions.filter(user=request.user).order_by("-submitted_at"))
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
        original_file_name = uploaded_file.name
        try:
            validate_uploaded_file(
                uploaded_file,
                allowed_extensions={
                    ".zip",
                    ".rar",
                    ".7z",
                    ".pdf",
                    ".txt",
                    ".doc",
                    ".docx",
                    ".png",
                    ".jpg",
                    ".jpeg",
                },
                max_size_mb=25,
            )
            randomize_uploaded_filename(uploaded_file)
        except ValidationError as exc:
            return JsonResponse({"success": False, "error": exc.messages[0]}, status=400)

    try:
        submission = AssignmentSubmission.objects.create(
            assignment=assignment,
            user=request.user,
            attempt_number=assignment.get_user_attempts(request.user) + 1,
            content=request.POST.get("content", ""),
        )

        if uploaded_file is not None:
            submission.attach_uploaded_file(uploaded_file, original_name=original_file_name)
            submission.save(update_fields=["files"])

        messages.success(request, pgettext("assignments.views.message", "assignment_submitted"))
        return JsonResponse(
            {
                "success": True,
                "message": pgettext("assignments.views.message", "assignment_submitted"),
                "submission_id": submission.id,
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


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
