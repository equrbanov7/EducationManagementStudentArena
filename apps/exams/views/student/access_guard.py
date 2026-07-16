"""Student attempt endpoint-ləri üçün mərkəzi davam icazəsi."""

from django.core.exceptions import PermissionDenied
from django.utils.translation import pgettext


def active_attempt_access_denial_reason(attempt, user):
    """Aktiv attempt artıq istifadəçiyə açıq deyilsə səbəbi qaytarır.

    Tenant və attempt sahibliyi view queryset-lərində yoxlanılır. Bu
    guard sonradan arxivlənən/deaktiv/silinən imtahanı və sonradan
    exclusion siyahısına salınan tələbəni bütün aktiv attempt yazma
    endpoint-lərində eyni qayda ilə bloklayır. Bitmiş attempt-lərə
    toxunmur ki, tarixi nəticə redirect-i və arxiv baxışı qorunsun.
    """
    if getattr(attempt, "is_finished", False):
        return None

    exam = attempt.exam
    if not exam.is_active or exam.is_archived or getattr(exam, "is_deleted", False):
        return pgettext("exams.model.access", "exam_not_active")

    if user != exam.author and exam.excluded_users.filter(pk=getattr(user, "pk", None)).exists():
        return pgettext("exams.model.access", "no_exam_access")

    return None


def ensure_active_attempt_access(attempt, user, *, request=None):
    """Access ləğv olunubsa student endpoint-ini 403 ilə dayandırır."""
    reason = active_attempt_access_denial_reason(attempt, user)
    if reason:
        raise PermissionDenied(reason)
    if request is not None and not getattr(attempt, "is_finished", False):
        from django.contrib.auth import logout

        from apps.exams.services.final_center import clear_entry_session, final_attempt_entry_session_valid

        if not final_attempt_entry_session_valid(request, attempt):
            clear_entry_session(request)
            logout(request)
            raise PermissionDenied(
                pgettext(
                    "exams.view.final_center.permission",
                    "Bu giriş sessiyası artıq etibarlı deyil. Nəzarətçinin verdiyi yeni PIN ilə daxil olun.",
                )
            )


__all__ = ["active_attempt_access_denial_reason", "ensure_active_attempt_access"]
