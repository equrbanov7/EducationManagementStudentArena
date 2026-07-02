"""
assignments/views/teacher.py
──────────────────────────
Teacher-facing views for assignments.

Contains:
- review_submissions
- grade_submission
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from apps.task_submission_core.review import (
    annotate_teacher_review_state,
    apply_submission_filters,
    build_pagination_query,
)
from apps.task_submission_core.services import apply_grade
from core.helpers import REVIEW_EDIT_LOCK_WINDOW, _safe_same_origin_redirect_path
from core.permissions import request_has_permission

from ..shared._helpers import _get_tenant_assignment_or_404, _get_tenant_submission_or_404, _teacher_review_back_url

logger = logging.getLogger(__name__)


def _can_delete_submissions(request):
    return (
        request_has_permission(request, "assignment.delete")
        or request_has_permission(request, "course.delete")
        or request_has_permission(request, "exam.delete")
    )


# ════════════════════════════════════════════════════════════════════════════
# Review Submissions
# ════════════════════════════════════════════════════════════════════════════


@login_required
def review_submissions(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Cavabları yoxlamaq (müəllim üçün)                                       │
    │ GET /assignments/<pk>/submissions/                                         │
    │                                                                         │
    │ Müəllim burada:                                                         │
    │ - Bütün tələbə cavablarını görür                                        │
    │ - Qiymət verə bilir                                                     │
    │ - Rəy yaza bilir                                                        │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    assignment = _get_tenant_assignment_or_404(request, pk)

    # İcazə yoxlaması
    if not request.user.is_teacher_or_above or assignment.course.owner != request.user:
        messages.error(request, pgettext("assignments.views.message", "permission_denied"))
        return redirect("courses:course_dashboard", course_id=assignment.course.id)

    submissions = assignment.submissions.select_related("user", "assignment__course__organization")
    submissions, filters = apply_submission_filters(
        submissions,
        request.GET,
        student_lookup_prefix="user",
        allowed_status_filters={"all", "submitted", "grading", "graded", "returned"},
    )
    submissions = submissions.order_by("-submitted_at")
    page_obj = Paginator(submissions, 12).get_page(request.GET.get("page"))
    selected_submission_raw = (request.GET.get("submission") or "").strip()
    selected_submission_id = selected_submission_raw if selected_submission_raw.isdigit() else ""
    pagination_query = build_pagination_query(
        filters=filters,
        selected_submission_id=selected_submission_id,
        from_section=request.GET.get("from_section"),
        return_to=request.GET.get("return_to"),
    )

    submissions_page = annotate_teacher_review_state(list(page_obj.object_list), student_attr="user")

    context = {
        "assignment": assignment,
        "submissions": submissions_page,
        "page_obj": page_obj,
        "selected_submission_id": selected_submission_id,
        "back_url": _teacher_review_back_url(request, assignment),
        "search_query": filters.search_query,
        "status_filter": filters.status_filter,
        "date_from": filters.date_from_raw,
        "date_to": filters.date_to_raw,
        "pagination_query": pagination_query,
        "can_delete_submissions": _can_delete_submissions(request),
    }

    return render(request, "assignments/review_submissions.html", context)


# ════════════════════════════════════════════════════════════════════════════
# Grade Submission
# ════════════════════════════════════════════════════════════════════════════


@login_required
@require_http_methods(["POST"])
def delete_submissions(request, pk):
    assignment = _get_tenant_assignment_or_404(request, pk)

    if not request.user.is_teacher_or_above or assignment.course.owner != request.user:
        messages.error(request, pgettext("assignments.views.message", "permission_denied"))
        return redirect(_teacher_review_back_url(request, assignment))

    if not _can_delete_submissions(request):
        messages.error(request, pgettext("assignments.views.message", "permission_denied"))
        return redirect(_teacher_review_back_url(request, assignment))

    redirect_url = _safe_same_origin_redirect_path(request, request.POST.get("next")) or _teacher_review_back_url(
        request, assignment
    )

    raw_ids = request.POST.getlist("submission_ids")
    single_submission_id = (request.POST.get("submission_id") or "").strip()
    if single_submission_id:
        raw_ids.append(single_submission_id)

    submission_ids = sorted({int(raw_id) for raw_id in raw_ids if str(raw_id).isdigit()})
    if not submission_ids:
        messages.warning(request, pgettext("assignments.views.message", "submission_not_found"))
        return redirect(redirect_url)

    submissions_qs = assignment.submissions.filter(id__in=submission_ids)
    if not submissions_qs.exists():
        messages.warning(request, pgettext("assignments.views.message", "submission_not_found"))
        return redirect(redirect_url)

    deleted_count = submissions_qs.count()
    submissions_qs.delete()
    messages.success(
        request,
        pgettext("assignments.views.message", "submissions_deleted").format(count=deleted_count),
    )
    return redirect(redirect_url)


@login_required
@require_http_methods(["POST"])
def grade_submission(request, pk):
    """
    ┌─────────────────────────────────────────────────────────────────────────┐
    │ Cavabı qiymətləndirmək                                                  │
    │ POST /assignments/submission/<pk>/grade/                                   │
    │                                                                         │
    │ Form data: grade, feedback (optional)                                   │
    └─────────────────────────────────────────────────────────────────────────┘
    """
    submission = _get_tenant_submission_or_404(request, pk)

    if not request_has_permission(request, "grade.input"):
        return JsonResponse(
            {"success": False, "error": pgettext("assignments.views.message", "permission_denied")},
            status=403,
        )

    # İcazə yoxlaması
    if not request.user.is_teacher_or_above or submission.assignment.course.owner != request.user:
        return JsonResponse(
            {"success": False, "error": pgettext("assignments.views.message", "permission_denied")},
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
        apply_grade(
            submission,
            request.POST.get("grade"),
            request.POST.get("feedback", ""),
            request.user,
            graded_status="graded",
            preserve_existing_graded_at=True,
        )

        messages.success(request, pgettext("assignment.message", "grade_given_successfully"))
        return JsonResponse({"success": True, "message": pgettext("assignment.message", "grade_given_successfully")})

    except Exception:
        logger.exception("Unexpected error in grade_submission (assignments)")
        return JsonResponse({"success": False, "error": "An unexpected error occurred."}, status=500)
