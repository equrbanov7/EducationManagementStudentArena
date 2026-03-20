"""
projects/views/_helpers.py
───────────────────────────
Project-specific helper functions.
"""

from urllib.parse import urlencode

from django.shortcuts import get_object_or_404

from apps.projects.models import Project, ProjectSubmission
from apps.task_submission_core.navigation import (
    build_student_task_back_url,
    build_teacher_review_back_url,
    student_return_to,
)
from core.helpers import _tenant_scoped_courses

# ════════════════════════════════════════════════════════════════════════════
# Tenant Scoping Functions
# ════════════════════════════════════════════════════════════════════════════


def _tenant_scoped_projects(request, queryset=None):
    """Return projects scoped to the current tenant."""
    base_queryset = queryset if queryset is not None else Project.objects.all()
    return base_queryset.filter(course__in=_tenant_scoped_courses(request))


def _tenant_scoped_submissions(request, queryset=None):
    """Return project submissions scoped to the current tenant."""
    base_queryset = queryset if queryset is not None else ProjectSubmission.objects.all()
    return base_queryset.filter(project__in=_tenant_scoped_projects(request))


def _get_tenant_course_or_404(request, course_id):
    """Get a course scoped to the current tenant or raise 404."""
    return get_object_or_404(_tenant_scoped_courses(request), id=course_id)


def _get_tenant_project_or_404(request, project_id):
    """Get a project scoped to the current tenant or raise 404."""
    return get_object_or_404(_tenant_scoped_projects(request), id=project_id)


def _get_tenant_submission_or_404(request, submission_id):
    """Get a submission scoped to the current tenant or raise 404."""
    return get_object_or_404(_tenant_scoped_submissions(request), id=submission_id)


# ════════════════════════════════════════════════════════════════════════════
# Navigation Helpers
# ════════════════════════════════════════════════════════════════════════════


def _project_back_url(request, project):
    """Generate the back URL for a project (for students)."""
    return build_student_task_back_url(request, course_id=project.course.id)


def _student_return_to(request):
    return student_return_to(request)


def _teacher_review_back_url(request, project):
    """Generate the back URL for teacher review page."""
    return build_teacher_review_back_url(request, course_id=project.course.id)


def _append_return_to(url, return_to):
    if not return_to:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'return_to': return_to})}"
