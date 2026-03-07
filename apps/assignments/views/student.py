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
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from core.upload_security import randomize_uploaded_filename, validate_uploaded_file

from ._helpers import _get_tenant_assignment_or_404, _assignment_back_url


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
    user_submissions = assignment.submissions.filter(student=request.user).order_by("-submitted_at")
    user_attempts = user_submissions.count()

    context = {
        "assignment": assignment,
        "user_submissions": user_submissions,
        "user_attempts": user_attempts,
        "can_submit": assignment.can_user_submit(request.user),
        "attempts_left": assignment.max_attempts - user_attempts,
        "back_url": _assignment_back_url(request, assignment),
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
    from apps.assignments.models import AssignmentSubmission

    assignment = _get_tenant_assignment_or_404(request, pk)

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
        submission = AssignmentSubmission.objects.create(
            assignment=assignment,
            student=request.user,
            content=request.POST.get("content", ""),
        )

        # Fayl yükləmə
        if uploaded_file is not None:
            submission.file = uploaded_file
            submission.save()

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
    submissions = assignment.submissions.filter(student=request.user).order_by("-submitted_at")
    user_attempts = submissions.count()

    context = {
        "assignment": assignment,
        "submissions": submissions,
        "user_attempts": user_attempts,
        "can_submit": assignment.can_user_submit(request.user),
        "attempts_left": assignment.max_attempts - user_attempts,
    }

    return render(request, "assignments/my_submissions.html", context)
