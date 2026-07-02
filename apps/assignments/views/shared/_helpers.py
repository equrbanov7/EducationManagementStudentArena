"""
assignments/views/_helpers.py
──────────────────────────────
Assignment-specific helper functions.
"""

from urllib.parse import urlencode

from django.shortcuts import get_object_or_404

from apps.assignments.models import Assignment, AssignmentSubmission
from apps.task_submission_core.public import (
    build_student_task_back_url,
    build_teacher_review_back_url,
    student_return_to,
)
from core.helpers import _tenant_scoped_courses

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
    return build_teacher_review_back_url(request, course_id=assignment.course.id)


def _student_return_to(request):
    return student_return_to(request)


def _assignment_back_url(request, assignment):
    """Generate the back URL for an assignment (for students)."""
    return build_student_task_back_url(request, course_id=assignment.course.id)


def _append_return_to(url, return_to):
    if not return_to:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'return_to': return_to})}"
