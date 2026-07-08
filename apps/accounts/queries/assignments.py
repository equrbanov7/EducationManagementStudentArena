"""
Assignment and membership queries for accounts.
"""

from django.db.models import Q

from apps.courses.models import Course, CourseMembership
from apps.exams.models import Exam


def get_assigned_courses_for_user(user, organization=None):
    """Return published courses assigned to the user as a student."""
    if not user:
        return Course.objects.none()

    queryset = Course.objects.filter(
        memberships__user=user,
        memberships__role="student",
        status="published",
    ).distinct()

    if organization is not None:
        queryset = queryset.filter(organization=organization)

    return queryset.select_related("owner").order_by("-created_at")


def get_assigned_exams_for_user(user, organization=None, active_only=True, include_public=True):
    """Return exams assigned to the user."""
    if not user:
        return Exam.objects.none()

    assignment_filter = (
        Q(allowed_users=user)
        | Q(allowed_groups__students=user)
        | Q(
            course__memberships__user=user,
            course__memberships__role="student",
            course__status="published",
        )
    )

    queryset = Exam.objects.filter(assignment_filter).exclude(excluded_users=user).distinct()
    if not include_public:
        queryset = queryset.filter(is_public=False)
    if active_only:
        queryset = queryset.filter(is_active=True)
    if organization is not None:
        queryset = queryset.filter(organization=organization)

    return queryset.select_related("author", "course").order_by("-created_at")


def get_course_membership_groups(user, course_ids):
    """Return a map of course id to normalized student group names."""
    if not user or not course_ids:
        return {}

    memberships = CourseMembership.objects.filter(
        course_id__in=course_ids,
        user=user,
        role="student",
    ).values_list("course_id", "group_name")

    course_groups = {}
    for course_id, group_name in memberships:
        normalized_group = (group_name or "").strip().lower()
        if not normalized_group:
            continue
        course_groups.setdefault(course_id, set()).add(normalized_group)

    return course_groups


__all__ = [
    "get_assigned_courses_for_user",
    "get_assigned_exams_for_user",
    "get_course_membership_groups",
]
