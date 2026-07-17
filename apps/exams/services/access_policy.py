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

    if not exam.is_public and exam.excluded_users.filter(id=user.id).exists():
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


def can_view_attempt_results(user):
    """Cəhd nəticəsini (YALNIZ GÖRMƏK) kim aça bilər?

    Müəllim öz imtahanlarının cəhdlərini görür; imtahan mərkəzi rolu (rəhbər +
    işçi) statistika bölməsindən "Bax" ilə org daxilindəki İSTƏNİLƏN imtahanın
    nəticəsinə (read-only, bal verə bilməz) baxa bilir. ``is_exam_center_user``
    və ``is_teacher_user`` hər ikisi superadmini əhatə edir.
    """
    return is_teacher_user(user) or is_exam_center_user(user)


def _ensure_can_view_attempt_results(user):
    if can_view_attempt_results(user):
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
# 2026-07 qaydası: final İLƏ YANAŞI midterm (kollokvium) imtahanını da yalnız
# imtahan mərkəzi YARADIR/çevirir (müəllimin yaratma formu bu kateqoriyaları
# təklif etmir; mövcud imtahanın redaktəsi qorunur).
SECURE_EXAM_CATEGORIES = frozenset({"final", "midterm"})


def is_exam_center_user(user):
    if user.is_superuser or getattr(user, "is_superadmin", False):
        return True
    return bool(getattr(user, "is_exam_center", False))


def can_manage_exam_rooms(user):
    """İmtahan zalı və zaldakı kompüter/MAC qeydlərini kim idarə edə bilər?

    Universitet qaydası: zal/kompüter qeydiyyatı yalnız SUPERADMIN səlahiyyətidir.
    Superadmin bunu ayrıca istifadəçiyə ``UserProfile.can_manage_exam_rooms``
    bayrağı ilə həvalə edə bilər (imtahan mərkəzi rolu TƏK BAŞINA kifayət
    etmir — mərkəz oturum/tələbə/PIN idarə edir, zal infrastrukturunu yox).
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or getattr(user, "is_superadmin", False):
        return True
    profile = getattr(user, "profile", None)
    return bool(profile is not None and getattr(profile, "can_manage_exam_rooms", False))


def ensure_can_manage_exam_rooms(user):
    if can_manage_exam_rooms(user):
        return
    raise PermissionDenied(pgettext("exams.service.access.permission", "exam_rooms_manage_superadmin_only"))


def can_assign_invigilators(user):
    """Zala nəzarətçi təyin edə bilən: superadmin + imtahan mərkəzi RƏHBƏRİ.

    İmtahan mərkəzi İŞÇİSİ (``exam_center_staff``) təyin ETMİR — yalnız monitor /
    PIN axtarışı / hesabat. Köhnə tək ``exam_center`` rolu rəhbərə bərabərdir.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or getattr(user, "is_superadmin", False):
        return True
    return bool(getattr(user, "is_exam_center_head", False))


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
    "can_assign_invigilators",
    "can_create_question_bank",
    "can_manage_exam_questions",
    "can_manage_exam_rooms",
    "can_manage_final_exam_content",
    "can_user_access_exam",
    "ensure_can_create_question_bank",
    "ensure_can_manage_exam_questions",
    "ensure_can_manage_exam_rooms",
    "is_exam_center_user",
    "is_teacher_user",
]
