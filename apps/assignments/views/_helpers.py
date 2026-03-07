"""
assignments/views/_helpers.py
──────────────────────────────
Assignment-specific helper functions.
"""

from urllib.parse import urlencode

from django.shortcuts import get_object_or_404
from django.urls import reverse

from apps.assignments.models import Assignment, AssignmentSubmission
from apps.courses.models import Course
from core.helpers import ASSIGNED_TASK_FILTER_CHOICES, _safe_same_origin_redirect_path, _tenant_scoped_courses


# ════════════════════════════════════════════════════════════════════════════
# Tenant Scoping Functions
# ════════════════════════════════════════════════════════════════════════════


def _tenant_scoped_assignments(request, queryset=None):
    """Return assignments scoped to the current tenant."""
    base_queryset = queryset if queryset is not None else Assignment.objects.all()
    return base_queryset.filter(course__in=_tenant_scoped_courses(request))


def _tenant_scoped_submissions(request, queryset=None):
    """Return assignment submissions scoped to the current tenant."""
    base_queryset = queryset if queryset is not None else AssignmentSubmission.objects.all()
    return base_queryset.filter(assignment__in=_tenant_scoped_assignments(request))


def _get_tenant_course_or_404(request, course_id):
    """Get a course scoped to the current tenant or raise 404."""
    return get_object_or_404(_tenant_scoped_courses(request), id=course_id)


def _get_tenant_assignment_or_404(request, assignment_id):
    """Get an assignment scoped to the current tenant or raise 404."""
    return get_object_or_404(_tenant_scoped_assignments(request), id=assignment_id)


def _get_tenant_submission_or_404(request, submission_id):
    """Get a submission scoped to the current tenant or raise 404."""
    return get_object_or_404(_tenant_scoped_submissions(request), id=submission_id)


# ════════════════════════════════════════════════════════════════════════════
# Navigation Helpers
# ════════════════════════════════════════════════════════════════════════════


def _teacher_review_back_url(request, assignment):
    """Generate the back URL for teacher review page."""
    explicit_return_url = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next"),
    )
    if explicit_return_url:
        return explicit_return_url

    source_section = (request.GET.get("from_section") or "").strip()
    if source_section in {"pending-review", "review-results"}:
        return f"{reverse('accounts:profile')}?section={source_section}"

    return reverse("courses:course_dashboard", kwargs={"course_id": assignment.course.id})


def _assignment_back_url(request, assignment):
    """Generate the back URL for an assignment (for students)."""
    source_section = (request.GET.get("from_section") or "").strip()
    if source_section == "assigned-exams":
        params = {"section": "assigned-exams"}
        assigned_type = (request.GET.get("assigned_type") or "").strip().lower()
        if assigned_type in ASSIGNED_TASK_FILTER_CHOICES:
            params["assigned_type"] = assigned_type
        return f"{reverse('accounts:profile')}?{urlencode(params)}"

    return reverse("courses:course_dashboard", kwargs={"course_id": assignment.course.id})
