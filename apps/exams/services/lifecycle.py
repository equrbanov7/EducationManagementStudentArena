"""İmtahan lifecycle keçidləri — atomik publish/unpublish (EXAM-P1-01, Seq3).

Problemlər (audit):
* köhnə yol çılpaq read-modify-write flip idi (``exam.is_active = not …; save()``)
  — iki tab/müəllim paralel basanda double-flip, tam ``save()`` paralel redaktəni
  clobber edir;
* publish qapısı yox idi — sualsız (boş) imtahan canlıya çıxa bilirdi;
* publish/unpublish audit-loglanmırdı (arxiv/silmə loglanırdı).

Həll: şərti-UPDATE state machine (final center pattern-i) — keçid yalnız
gözlənilən köhnə vəziyyətdən mümkündür; yarışda uduzan tərəf üçün rowcount=0
(no-op) qayıdır və çağıran "vəziyyət artıq dəyişib" bildirişi göstərir.
"""

from django.db import transaction
from django.utils.translation import pgettext

from apps.exams.services.language_parity import language_parity_error_message


def exam_publish_gate_error(exam) -> str:
    """Publish qapısı: imtahan tələbəyə çıxarıla bilməzsə səbəb mesajı, əks halda ""."""
    if exam.is_deleted:
        return pgettext("exams.service.lifecycle", "Silinmiş imtahan dərc edilə bilməz.")
    if not exam.questions.filter(is_active=True).exists():
        return pgettext(
            "exams.service.lifecycle",
            "İmtahanda heç bir aktiv sual yoxdur — dərc etməzdən əvvəl sual əlavə edin.",
        )
    return language_parity_error_message(exam) or ""


def _log_lifecycle(exam, by_user, request, *, reason, new_values):
    from apps.audit.public import log_action
    from core.constants import AuditAction

    log_action(
        action=AuditAction.UPDATE,
        user=by_user,
        organization=exam.organization,
        obj=exam,
        new_values=new_values,
        reason=reason,
        request=request,
    )


@transaction.atomic
def publish_exam(exam, *, by_user=None, request=None):
    """İmtahanı atomik dərc et.

    Qaytarır ``(changed, error)``: qapı keçilməsə ``(False, mesaj)``; başqa
    tab/proses artıq dərc edibsə (yarış) ``(False, "")``; uğurda ``(True, "")``.
    """
    # Parent row is the lock-order root for publish and question mutations.
    # This prevents a stale Exam instance from making the gate decision and
    # serializes with delete/deactivate services. Active question rows are also
    # locked so a concurrent delete cannot pass between gate and state update.
    locked_exam = type(exam).objects.select_for_update().get(pk=exam.pk)
    if locked_exam.is_active:
        exam.is_active = True
        exam.is_deleted = locked_exam.is_deleted
        return False, ""

    list(locked_exam.questions.filter(is_active=True).select_for_update().order_by("pk").values_list("pk", flat=True))
    error = exam_publish_gate_error(locked_exam)
    if error:
        return False, error
    updated = type(exam).objects.filter(pk=locked_exam.pk, is_active=False, is_deleted=False).update(is_active=True)
    exam.refresh_from_db(fields=["is_active", "is_deleted"])
    if not updated:
        return False, ""
    _log_lifecycle(locked_exam, by_user, request, reason="exam_published", new_values={"is_active": "True"})
    return True, ""


@transaction.atomic
def unpublish_exam(exam, *, by_user=None, request=None):
    """İmtahanı atomik deaktiv et. Qaytarır ``changed`` (yarışda uduzanda False)."""
    locked_exam = type(exam).objects.select_for_update().get(pk=exam.pk)
    updated = type(exam).objects.filter(pk=locked_exam.pk, is_active=True).update(is_active=False)
    exam.refresh_from_db(fields=["is_active"])
    if not updated:
        return False
    _log_lifecycle(locked_exam, by_user, request, reason="exam_unpublished", new_values={"is_active": "False"})
    return True


@transaction.atomic
def set_results_hidden(exam, hidden, *, by_user=None, request=None):
    """Nəticə görünürlüyünü atomik dəyiş (nəticə-publish keçidi).

    Qaytarır ``changed`` — başqa tab artıq eyni vəziyyətə keçiribsə False.
    """
    locked_exam = type(exam).objects.select_for_update().get(pk=exam.pk)
    updated = (
        type(exam)
        .objects.filter(pk=locked_exam.pk, results_hidden_from_students=not hidden)
        .update(results_hidden_from_students=hidden)
    )
    exam.refresh_from_db(fields=["results_hidden_from_students"])
    if not updated:
        return False
    _log_lifecycle(
        locked_exam,
        by_user,
        request,
        reason="exam_results_hidden" if hidden else "exam_results_published",
        new_values={"results_hidden_from_students": str(hidden)},
    )
    return True


__all__ = ["exam_publish_gate_error", "publish_exam", "unpublish_exam", "set_results_hidden"]
