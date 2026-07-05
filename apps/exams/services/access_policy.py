from django.core.exceptions import PermissionDenied
from django.utils.translation import pgettext

from core.roles import ProfileRole


def is_teacher_user(user):
    if user.is_superuser or getattr(user, "is_superadmin", False):
        return True

    # Organization admins/owners can legitimately manage exams too. Rely on
    # the active tenant role hierarchy instead of only the legacy teacher flags.
    if hasattr(user, "is_teacher_or_above"):
        return bool(getattr(user, "is_teacher_or_above", False))

    if hasattr(user, "has_role"):
        return user.has_role(ProfileRole.TEACHER) or user.has_role(ProfileRole.ASSISTANT_TEACHER)

    return False


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
        # M2 (2026-07-02): lazy lookup — exams→courses import kənarını kəsir.
        from django.apps import apps as django_apps

        CourseMembership = django_apps.get_model("courses", "CourseMembership")
        return CourseMembership.objects.filter(course=exam.course, user=user, role="student").exists()

    return False


def _ensure_teacher(user):
    if is_teacher_user(user):
        return
    raise PermissionDenied(pgettext("exams.service.attempt.permission", "teachers_only_page"))


# ---------------------------------------------------------------------------
# İmtahan mərkəzi siyasəti
# ---------------------------------------------------------------------------
# Universitet qaydası: FINAL imtahanın sual məzmununu (yükləmə, redaktə, bank
# qoşma, AI generasiya) yalnız "imtahan mərkəzi" rolu idarə edir; sual bankları
# da yalnız imtahan mərkəzi tərəfindən yaradılır. Müəllim quiz/midterm və
# kateqoriyasız imtahanların məzmununu idarə etməkdə sərbəstdir.
FINAL_EXAM_CATEGORY = "final"


def is_exam_center_user(user):
    if user.is_superuser or getattr(user, "is_superadmin", False):
        return True
    return bool(getattr(user, "is_exam_center", False))


def can_manage_final_exam_content(user):
    return is_exam_center_user(user)


def can_manage_exam_questions(user, exam):
    """Bu istifadəçi verilmiş imtahanın sual məzmununa toxuna bilərmi?"""
    if getattr(exam, "exam_type_extended", None) == FINAL_EXAM_CATEGORY:
        return can_manage_final_exam_content(user)
    return True


def ensure_can_manage_exam_questions(user, exam):
    if can_manage_exam_questions(user, exam):
        return
    raise PermissionDenied(pgettext("exams.service.access.permission", "final_exam_questions_exam_center_only"))


def can_create_question_bank(user):
    return is_exam_center_user(user)


def ensure_can_create_question_bank(user):
    if can_create_question_bank(user):
        return
    raise PermissionDenied(pgettext("exams.service.access.permission", "question_bank_create_exam_center_only"))


__all__ = [
    "FINAL_EXAM_CATEGORY",
    "_ensure_teacher",
    "can_create_question_bank",
    "can_manage_exam_questions",
    "can_manage_final_exam_content",
    "can_user_access_exam",
    "ensure_can_create_question_bank",
    "ensure_can_manage_exam_questions",
    "is_exam_center_user",
    "is_teacher_user",
]
