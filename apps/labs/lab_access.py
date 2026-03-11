from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.courses.models import CourseMembership
from core.helpers import REVIEW_EDIT_LOCK_WINDOW

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


def can_user_access_course_roster(user, course):
    """
    User must be the course owner or have teacher/assistant membership.
    """
    if course.owner == user:
        return True

    return CourseMembership.objects.filter(
        course=course,
        user=user,
        role__in=["teacher", "assistant"],
    ).exists()


def resolve_recheck_window(submission, *, current_time=None):
    if submission.status != "graded" or not submission.graded_at:
        return False, 0

    now = current_time or timezone.now()
    reveal_at = submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
    if now >= reveal_at:
        return False, 0

    return True, max(0, int((reveal_at - now).total_seconds()))


def resolve_identity_window(submission, *, current_time=None):
    now = current_time or timezone.now()

    if submission.status == "graded" and submission.graded_at:
        reveal_at = submission.graded_at + REVIEW_EDIT_LOCK_WINDOW
    elif submission.submitted_at:
        reveal_at = submission.submitted_at + REVIEW_EDIT_LOCK_WINDOW
    else:
        return False, 0

    if now >= reveal_at:
        return False, 0

    return True, max(0, int((reveal_at - now).total_seconds()))


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
