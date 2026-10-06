"""Student attempt endpoint-ləri üçün mərkəzi davam icazəsi."""

from django.core.exceptions import PermissionDenied
from django.db.models import Exists, OuterRef
from django.utils.translation import pgettext

# Perf 2026-10-06 (autosave qaynar yolu): exclusion yoxlaması attempt-i yükləyən
# SORĞUNUN ÖZÜNDƏ `EXISTS` annotasiyası kimi gəlir — guard ayrıca round-trip
# etmir. Annotasiya yalnız `user_exclusion_annotation(user)` ilə, guard-a
# ötürülən HƏMİN istifadəçi üçün qurulur (bax `ensure_active_attempt_access`).
USER_EXCLUDED_ANNOTATION = "access_user_excluded"


def user_exclusion_annotation(user):
    """``{USER_EXCLUDED_ANNOTATION: Exists(...)}`` — attempt queryset-inə ``.annotate(**…)`` üçün."""
    from apps.exams.models import Exam

    through = Exam.excluded_users.through
    return {
        USER_EXCLUDED_ANNOTATION: Exists(
            through.objects.filter(exam_id=OuterRef("exam_id"), user_id=getattr(user, "pk", None))
        )
    }


def active_attempt_access_denial_reason(attempt, user, *, user_excluded=None):
    """Aktiv attempt artıq istifadəçiyə açıq deyilsə səbəbi qaytarır.

    Tenant və attempt sahibliyi view queryset-lərində yoxlanılır. Bu
    guard sonradan arxivlənən/deaktiv/silinən imtahanı və sonradan
    exclusion siyahısına salınan tələbəni bütün aktiv attempt yazma
    endpoint-lərində eyni qayda ilə bloklayır. Bitmiş attempt-lərə
    toxunmur ki, tarixi nəticə redirect-i və arxiv baxışı qorunsun.

    ``user_excluded`` — çağıran exclusion-u attempt sorğusunda artıq hesablayıbsa
    (``user_exclusion_annotation``) onun nəticəsi; ``None`` → ayrıca sorğu.
    """
    if getattr(attempt, "is_finished", False):
        return None

    exam = attempt.exam
    if not exam.is_active or exam.is_archived or getattr(exam, "is_deleted", False):
        return pgettext("exams.model.access", "exam_not_active")

    # Perf 2026-10-06: müəllif müqayisəsi id ilə — `exam.author` obyektini
    # yükləmək üçün ayrıca `auth_user` sorğusu getmir (Model `==` də pk müqayisəsidir).
    user_pk = getattr(user, "pk", None)
    is_author = user_pk is not None and user_pk == exam.author_id
    if not is_author:
        if user_excluded is None:
            user_excluded = exam.excluded_users.filter(pk=user_pk).exists()
        if user_excluded:
            return pgettext("exams.model.access", "no_exam_access")

    return None


def final_entry_session_revoked(request, attempt):
    """Final-mərkəz attempt-inin giriş sessiyası artıq etibarlı deyilsə True."""
    if request is None or getattr(attempt, "is_finished", False):
        return False
    from apps.exams.services.final_center import final_attempt_entry_session_valid

    return not final_attempt_entry_session_valid(request, attempt)


def revoke_final_entry_session(request):
    """Etibarsız giriş sessiyasını bağlayır (çıxış) və 403 qaldırır.

    Tranzaksiyadan KƏNARDA çağırılmalıdır — `logout`-un sessiya silməsi geri
    qaytarılan atomic blokla birlikdə itməsin.
    """
    from django.contrib.auth import logout

    from apps.exams.services.final_center import clear_entry_session

    clear_entry_session(request)
    logout(request)
    raise PermissionDenied(
        pgettext(
            "exams.view.final_center.permission",
            "Bu giriş sessiyası artıq etibarlı deyil. Nəzarətçinin verdiyi yeni PIN ilə daxil olun.",
        )
    )


def ensure_active_attempt_access(attempt, user, *, request=None, user_excluded=None):
    """Access ləğv olunubsa student endpoint-ini 403 ilə dayandırır."""
    reason = active_attempt_access_denial_reason(attempt, user, user_excluded=user_excluded)
    if reason:
        raise PermissionDenied(reason)
    if final_entry_session_revoked(request, attempt):
        revoke_final_entry_session(request)


__all__ = [
    "USER_EXCLUDED_ANNOTATION",
    "active_attempt_access_denial_reason",
    "ensure_active_attempt_access",
    "final_entry_session_revoked",
    "revoke_final_entry_session",
    "user_exclusion_annotation",
]
