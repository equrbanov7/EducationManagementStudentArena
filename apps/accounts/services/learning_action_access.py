"""Eligibility for creating items from a personal teaching cabinet."""

from apps.exams.public import is_exam_center_user, is_teacher_user
from core.permissions import request_has_permission


def can_create_personal_exam(request):
    return (
        not getattr(request, "is_view_as", False)
        and getattr(request, "user", None) is not None
        and is_teacher_user(request.user)
        and request_has_permission(request, "exam.create")
    )


def can_create_personal_course(request):
    return not getattr(request, "is_view_as", False) and request_has_permission(request, "course.create")


def can_send_personal_questions(request):
    return (
        not getattr(request, "is_view_as", False)
        and getattr(request, "user", None) is not None
        and is_teacher_user(request.user)
        and not is_exam_center_user(request.user)
    )
