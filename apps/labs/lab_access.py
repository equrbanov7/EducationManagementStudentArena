from django.core.exceptions import PermissionDenied

from apps.courses.models import CourseMembership
from apps.task_submission_core.public import (
    can_user_access_course_roster,
    resolve_identity_window,
    resolve_recheck_window,
)

from .models import LabSubmission


def can_student_access_lab(lab, user):
    return lab.can_student_access(user)


def can_teacher_access_lab(lab, user):
    return lab.can_teacher_access(user)


def ensure_student_can_access_lab(lab, user):
    if not can_student_access_lab(lab, user):
        raise PermissionDenied("You do not have permission to access this lab.")


def ensure_teacher_can_access_lab(lab, user, *, message="You do not have permission to access this lab."):
    if not can_teacher_access_lab(lab, user):
        raise PermissionDenied(message)


def get_lab_submissions(lab, status=None, group_name=None):
    qs = LabSubmission.objects.filter(assignment__lab=lab).select_related(
        "assignment__student",
        "assignment__student__profile",
        "graded_by",
    )

    if status:
        qs = qs.filter(status=status)

    if group_name:
        student_ids = CourseMembership.objects.filter(
            course=lab.course,
            role="student",
            group_name=group_name,
        ).values_list("user_id", flat=True)
        qs = qs.filter(assignment__student_id__in=student_ids)

    return qs.order_by("-submitted_at")


def get_pending_lab_submissions(teacher, organization=None):
    qs = LabSubmission.objects.filter(
        assignment__lab__created_by=teacher,
        status="submitted",
    ).select_related("assignment__lab", "assignment__student")

    if organization is not None:
        qs = qs.filter(assignment__lab__course__organization=organization)

    return qs.order_by("submitted_at")


__all__ = [
    "can_student_access_lab",
    "can_teacher_access_lab",
    "can_user_access_course_roster",
    "ensure_student_can_access_lab",
    "ensure_teacher_can_access_lab",
    "get_lab_submissions",
    "get_pending_lab_submissions",
    "resolve_identity_window",
    "resolve_recheck_window",
]
