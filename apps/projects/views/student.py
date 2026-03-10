"""
projects/views/student.py
──────────────────────────
Student-facing views for projects.

Contains:
- project_detail
- submit_project
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

from core.helpers import REVIEW_EDIT_LOCK_WINDOW
from core.upload_security import randomize_uploaded_filename, validate_uploaded_file

from ._helpers import _append_return_to, _get_tenant_project_or_404, _project_back_url, _student_return_to


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
# Project Detail (Student)
# ════════════════════════════════════════════════════════════════════════════


@login_required
def project_detail(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işinin detalları (tələbə üçün)                                     │
    │ GET /projects/<pk>/                                                     │
    │                                                                         │
    │ Tələbə burada:                                                          │
    │ - Project məlumatlarını görür                                           │
    │ - Əvvəlki cavablarını görür                                             │
    │ - Yeni cavab göndərə bilir (cəhd varsa)                                 │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = _get_tenant_project_or_404(request, pk)

    # ─────────────────────────────────────────────────────────────────────────
    # İcazə yoxlaması - tələbə yalnız özünə təyin olunmuşlara baxa bilər
    # ─────────────────────────────────────────────────────────────────────────
    if getattr(request.user, "is_student", False):
        has_access = project.assigned_students.filter(id=request.user.id).exists()
        if not has_access:
            messages.error(request, pgettext("projects.views.message", "no_project_access"))
            return redirect("courses:course_dashboard", course_id=project.course.id)

    # İstifadəçinin əvvəlki cavablarını al
    user_submissions = _annotate_review_state(project.submissions.filter(student=request.user).order_by("-submitted_at"))
    user_attempts = len(user_submissions)
    return_to_url = _student_return_to(request)

    context = {
        "project": project,
        "user_submissions": user_submissions,
        "user_attempts": user_attempts,
        "can_submit": project.can_user_submit(request.user),
        "attempts_left": project.max_attempts - user_attempts,
        "back_url": _project_back_url(request, project),
        "results_url": _append_return_to(f"/projects/{project.id}/my-submissions/", return_to_url),
        "review_window_minutes": REVIEW_WINDOW_MINUTES,
    }

    return render(request, "projects/project_detail.html", context)


# ════════════════════════════════════════════════════════════════════════════
# Submit Project
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["POST"])
def submit_project(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Kurs işinə cavab göndərmək                                              │
    │ POST /projects/<pk>/submit/                                             │
    │                                                                         │
    │ Form data: content (text), file (optional)                              │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    from apps.projects.models import ProjectSubmission

    project = _get_tenant_project_or_404(request, pk)

    if not project.assigned_students.filter(id=request.user.id).exists():
        return JsonResponse(
            {
                "success": False,
                "error": pgettext("projects.views.message", "submit_not_allowed"),
            },
            status=403,
        )

    # Cavab göndərə bilərmi yoxla
    if not project.can_user_submit(request.user):
        return JsonResponse(
            {
                "success": False,
                "error": pgettext("projects.views.message", "submit_not_allowed"),
            },
            status=400,
        )

    uploaded_file = request.FILES.get("file")
    if uploaded_file is not None:
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
        submission = ProjectSubmission.objects.create(
            project=project,
            student=request.user,
            content=request.POST.get("content", ""),
        )

        # Fayl yükləmə
        if uploaded_file is not None:
            submission.file = uploaded_file
            submission.save()

        messages.success(request, pgettext("projects.views.message", "project_submitted"))
        return JsonResponse(
            {
                "success": True,
                "message": pgettext("projects.views.message", "project_submitted"),
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
    │ GET /projects/<pk>/my-submissions/                                      │
    │                                                                         │
    │ Tələbə burada:                                                          │
    │ - Bütün göndərdiyi cavabları görür                                      │
    │ - Qiymətlərini görür                                                    │
    │ - Müəllim rəyini görür                                                  │
    │ - Qalan cəhd sayını görür                                               │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    project = _get_tenant_project_or_404(request, pk)

    # ─────────────────────────────────────────────────────────────────────────
    # İcazə yoxlaması - yalnız özünə təyin olunmuş project-lərə baxa bilər
    # ─────────────────────────────────────────────────────────────────────────
    if not project.assigned_students.filter(id=request.user.id).exists():
        messages.error(request, pgettext("projects.views.message", "no_project_access"))
        return redirect("courses:course_dashboard", course_id=project.course.id)

    # İstifadəçinin cavablarını al
    submissions = _annotate_review_state(project.submissions.filter(student=request.user).order_by("-submitted_at"))
    user_attempts = len(submissions)
    return_to_url = _student_return_to(request)

    context = {
        "project": project,
        "submissions": submissions,
        "user_attempts": user_attempts,
        "can_submit": project.can_user_submit(request.user),
        "attempts_left": project.max_attempts - user_attempts,
        "back_url": _project_back_url(request, project),
        "detail_url": _append_return_to(f"/projects/{project.id}/", return_to_url),
        "review_window_minutes": REVIEW_WINDOW_MINUTES,
    }

    return render(request, "projects/my_submissions.html", context)
