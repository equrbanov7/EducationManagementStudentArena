"""
assignments/views/teacher.py
──────────────────────────
Teacher-facing views for assignments.

Contains:
- review_submissions
- grade_submission
"""

from datetime import datetime
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods

from core.helpers import REVIEW_EDIT_LOCK_WINDOW, _safe_same_origin_redirect_path
from core.permissions import request_has_permission

from ._helpers import _get_tenant_assignment_or_404, _get_tenant_submission_or_404, _teacher_review_back_url


def _parse_filter_date(raw_value):
    raw_date = (raw_value or "").strip()
    if not raw_date:
        return "", None
    try:
        return raw_date, datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return "", None


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

    submissions = assignment.submissions.select_related("user")
    search_query = (request.GET.get("q") or "").strip()
    if search_query:
        submissions = submissions.filter(
            Q(user__username__icontains=search_query)
            | Q(user__first_name__icontains=search_query)
            | Q(user__last_name__icontains=search_query)
            | Q(content__icontains=search_query)
        )

    status_filter = (request.GET.get("status") or "all").strip().lower()
    allowed_status_filters = {"all", "submitted", "grading", "graded", "returned"}
    if status_filter not in allowed_status_filters:
        status_filter = "all"
    if status_filter != "all":
        submissions = submissions.filter(status=status_filter)

    date_from_raw, date_from = _parse_filter_date(request.GET.get("date_from"))
    date_to_raw, date_to = _parse_filter_date(request.GET.get("date_to"))
    if date_from:
        submissions = submissions.filter(submitted_at__date__gte=date_from)
    if date_to:
        submissions = submissions.filter(submitted_at__date__lte=date_to)

    submissions = submissions.order_by("-submitted_at")
    page_obj = Paginator(submissions, 12).get_page(request.GET.get("page"))
    selected_submission_raw = (request.GET.get("submission") or "").strip()
    selected_submission_id = selected_submission_raw if selected_submission_raw.isdigit() else ""
    pagination_query = urlencode(
        {
            key: value
            for key, value in {
                "q": search_query,
                "status": status_filter,
                "date_from": date_from_raw,
                "date_to": date_to_raw,
                "submission": selected_submission_id,
                "from_section": (request.GET.get("from_section") or "").strip(),
                "return_to": (request.GET.get("return_to") or "").strip(),
            }.items()
            if value not in ("", None)
        }
    )

    context = {
        "assignment": assignment,
        "submissions": page_obj.object_list,
        "page_obj": page_obj,
        "selected_submission_id": selected_submission_id,
        "back_url": _teacher_review_back_url(request, assignment),
        "search_query": search_query,
        "status_filter": status_filter,
        "date_from": date_from_raw,
        "date_to": date_to_raw,
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
        submission.grade = request.POST.get("grade")
        submission.feedback = request.POST.get("feedback", "")
        submission.status = "graded"
        if not submission.graded_at:
            submission.graded_at = timezone.now()
        submission.graded_by = request.user
        submission.save()

        messages.success(request, pgettext("assignments.views.message", "grade_given"))
        return JsonResponse({"success": True, "message": pgettext("assignments.views.message", "grade_given")})

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
