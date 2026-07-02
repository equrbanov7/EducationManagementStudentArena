"""
Tenant scoping helpers.

Resolve the active organization, bind active-role context to a user, and
scope course/exam querysets to the request's organization (tenant isolation).
"""

from apps.courses.models import Course
from apps.exams.models import Exam
from apps.exams.public import without_disabled_practical_exams
from core.tenancy import get_request_organization, scoped_by_organization

from ...queries import get_assigned_courses_for_user, get_assigned_exams_for_user


def _get_active_organization(request):
    """
    Use middleware-selected organization first; fallback to profile organization.
    """
    return get_request_organization(request)


def _bind_active_role_context(user, organization, *, memberships=None, permissions=None):
    if user and hasattr(user, "set_active_organization_context"):
        user.set_active_organization_context(
            organization,
            memberships=memberships,
            permissions=permissions,
        )
    return user


def _tenant_scoped_courses(request, queryset=None):
    base_queryset = queryset if queryset is not None else Course.objects.all()
    return scoped_by_organization(base_queryset, request)


def _tenant_scoped_exams(request, queryset=None):
    base_queryset = queryset if queryset is not None else Exam.objects.all()
    return without_disabled_practical_exams(scoped_by_organization(base_queryset, request))


def _assigned_courses_queryset(request, user):
    return _tenant_scoped_courses(request, get_assigned_courses_for_user(user))


def _assigned_exams_queryset(request, user, *, active_only=True):
    return _tenant_scoped_exams(
        request,
        get_assigned_exams_for_user(user, active_only=active_only, include_public=False),
    ).distinct()
