"""
Student-facing dashboard and assigned-items / results views.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.assignments.models import Assignment, Submission
from core.tenancy import restore_request_organization_from_profile

from .._dashboard_helpers import _collect_my_results
from .._helpers import (
    _assigned_courses_queryset,
    _assigned_exams_queryset,
    _query_string,
    _render_profile_section,
    _role_capabilities,
)

User = get_user_model()


@login_required
def student_dashboard(request):
    """
    Student dashboard with enrolled courses, assignments, and upcoming exams.
    """
    # Get enrolled courses
    enrolled_courses = _assigned_courses_queryset(request, request.user)[:6]

    now = timezone.now()

    # Get pending assignments
    pending_assignments = (
        Assignment.objects.filter(
            course__in=enrolled_courses,
            assigned_students=request.user,
            due_date__gte=now,
            status__in=["published", "active"],
        )
        .distinct()
        .order_by("due_date")[:5]
    )
    pending_assignments = list(pending_assignments)
    for assignment in pending_assignments:
        days_until_deadline = (assignment.due_date - now).total_seconds() / 86400
        assignment.deadline_badge_variant = (
            "urgent" if days_until_deadline <= 1 else "soon" if days_until_deadline <= 3 else "normal"
        )

    # Get upcoming exams
    upcoming_exams = (
        _assigned_exams_queryset(request, request.user, active_only=True)
        .filter(start_datetime__gte=now)
        .order_by("start_datetime")[:5]
    )

    # Get recent grades
    recent_grades = Submission.objects.filter(user=request.user, status="graded").order_by("-graded_at")[:5]

    context = {
        "enrolled_courses": enrolled_courses,
        "pending_assignments": pending_assignments,
        "upcoming_exams": upcoming_exams,
        "recent_grades": recent_grades,
    }

    return render(request, "accounts/student_dashboard.html", context)


@login_required
def assigned_exams(request):
    """Assigned exams list for the current user."""
    profile = getattr(request.user, "profile", None)
    restore_request_organization_from_profile(request, profile=profile)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    exams = _assigned_exams_queryset(request, request.user, active_only=True).order_by("-start_datetime", "-created_at")

    search = request.GET.get("search", "")
    if search:
        exams = exams.filter(Q(title__icontains=search) | Q(description__icontains=search))

    exam_items = []
    for exam in exams:
        can_start_without_code, _ = exam.can_user_start(request.user, code=None)
        exam_items.append(
            {
                "exam": exam,
                "requires_code": bool(exam.access_code and not can_start_without_code),
            }
        )

    context = {
        "exam_items": exam_items,
        "search_query": search,
    }
    return render(request, "accounts/assigned_exams.html", context)


@login_required
def assigned_courses(request):
    """Assigned courses list for the current user."""
    profile = getattr(request.user, "profile", None)
    restore_request_organization_from_profile(request, profile=profile)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    courses = _assigned_courses_queryset(request, request.user).order_by("-created_at")

    search = request.GET.get("search", "")
    if search:
        courses = courses.filter(Q(title__icontains=search) | Q(description__icontains=search))

    context = {
        "courses": courses,
        "search_query": search,
    }
    return render(request, "accounts/assigned_courses.html", context)


@login_required
def my_results(request):
    """Unified submission/result list for students and member-level users."""
    profile = getattr(request.user, "profile", None)
    restore_request_organization_from_profile(request, profile=profile)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    from django.core.paginator import Paginator

    search_query = (request.GET.get("q") or "").strip()
    items, counts, active_filter = _collect_my_results(
        request, filter_type=request.GET.get("type"), search=search_query
    )

    paginator = Paginator(items, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "items": page_obj,
        "page_obj": page_obj,
        "counts": counts,
        "active_filter": active_filter,
        "search_query": search_query,
        "pagination_query": _query_string(type=active_filter, q=search_query),
    }
    return render(request, "accounts/my_results.html", context)


@login_required
def pending_answers(request):
    """Pending (not yet finalized) answer list for students."""
    profile = getattr(request.user, "profile", None)
    restore_request_organization_from_profile(request, profile=profile)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    return _render_profile_section(request, "pending-answers")
