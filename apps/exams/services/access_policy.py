from django.core.exceptions import PermissionDenied
from django.utils.translation import pgettext

from apps.accounts.models import ProfileRole


def is_teacher_user(user):
    if user.is_superuser or getattr(user, "is_superadmin", False):
        return True

    if hasattr(user, "has_role"):
        if user.has_role(ProfileRole.TEACHER) or user.has_role(ProfileRole.ASSISTANT_TEACHER):
            return True

    profile = getattr(user, "profile", None)
    return getattr(profile, "role", None) in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}


def can_user_access_exam(exam, user):
    if is_teacher_user(user) or exam.author == user:
        return True

    if not exam.is_active:
        return False

    if exam.allowed_users.filter(id=user.id).exists():
        return True

    if exam.allowed_groups.filter(students=user).exists():
        return True

    if exam.course:
        from apps.courses.models import CourseMembership

        return CourseMembership.objects.filter(course=exam.course, user=user, role="student").exists()

    return False


def _ensure_teacher(user):
    if is_teacher_user(user):
        return
    raise PermissionDenied(pgettext("exams.service.attempt.permission", "teachers_only_page"))


__all__ = [
    "_ensure_teacher",
    "can_user_access_exam",
    "is_teacher_user",
]
