"""Aktiv imtahanın publish qapısını sual mutasiyalarında qoruyur.

Qayda: dərc olunmuş (aktiv) imtahanda ən azı bir aktiv sual qalmalıdır (publish
qapısı ilə eyni invariant, bax ``services/lifecycle.py``).

QB 2026-09-30 (sahib): canlı imtahandan sonra müəllim bütün sualları seçib silə
bilmirdi — xəta dalana dirənirdi və mətni «aktiv istifadəçi» kimi başa düşülürdü.
İndi seçim imtahanın BÜTÜN aktiv suallarını əhatə edəndə:

* imtahan hazırda istifadədədirsə (açıq cəhd / canlı sessiya / final zal oturumu)
  → ``ExamInUse`` (səbəb adlandırılır, heç nə dəyişmir);
* əks halda təsdiq tələb olunur → ``ActiveExamRequiresQuestion``; çağıran
  ``deactivate_exam=True`` ilə təkrar göndərəndə imtahan (audit loglu
  ``unpublish_exam``) və suallar BİR tranzaksiyada dəyişir.

Təhlükəsizlik baxışı 2026-09-30 (H1/H2): ``ExamAnswer.question`` və
``AppealItem.question`` ``CASCADE``-dir — sualı SİLMƏK təqdim olunmuş cəhdlərin
cavablarını və apellyasiya bəndlərini də silir. Ona görə HƏR silmədə (təkcə «son
suallar» halında yox):

* imtahan istifadədədirsə → ``ExamInUse`` (yazılan cəhdin cavabı itməsin);
* suala cavab və ya apellyasiya bağlıdırsa → ``QuestionsHaveAnswers`` — silinmir,
  müəllimə deaktiv etmək təklif olunur (cavablar və nəticələr qalır).

Deaktivasiya əvvəlki kimidir (məlumat silmir).

Sahib 2026-11-11: toplu silmədə seçimin bir hissəsi istifadə olunubsa müəllim dalana dirənmir —
``QuestionsHaveAnswers`` neçə sualın istifadə olunduğunu (``used_count``) və neçəsinin silinə biləcəyini
(``unused_count``) daşıyır; çağıran ``on_used="deactivate"`` ilə təkrar göndərəndə istifadə olunmuş suallar
DEAKTİV edilir (cavablar qalır), qalanları silinir — bir tranzaksiyada. Toplu əməllər audit olunur.
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext

from apps.exams.services.exam_usage import exam_in_use_error
from apps.exams.services.lifecycle import unpublish_exam

MODE_DELETE = "delete"
MODE_DEACTIVATE = "deactivate"


class ActiveExamRequiresQuestion(ValidationError):
    """Seçim aktiv imtahanın bütün aktiv suallarını əhatə edir — imtahan deaktiv edilməlidir."""


class ExamInUse(ValidationError):
    """İmtahan hazırda istifadədədir — avtomatik deaktivasiya qadağandır."""


class QuestionsHaveAnswers(ValidationError):
    """Silinəcək suallara tələbə cavabı / apellyasiya bağlıdır — silmək tarixçəni məhv edər."""

    used_count = 0
    unused_count = 0


ON_USED_REFUSE = "refuse"
ON_USED_DEACTIVATE = "deactivate"
AUDIT_RESOURCE = "exam_question_bulk"


@dataclass(frozen=True)
class QuestionMutationOutcome:
    count: int
    exam_deactivated: bool = False
    # ``on_used="deactivate"`` ilə silmədə: silinə bilməyib deaktiv edilən (istifadə olunmuş) suallar.
    deactivated_used: int = 0


def active_exam_question_invariant_message() -> str:
    return pgettext(
        "exams.service.lifecycle",
        "Seçilmiş suallar bu dərc olunmuş (aktiv) imtahanın son aktiv suallarıdır. Onları silmək və ya "
        "deaktiv etmək üçün imtahan da deaktiv edilməlidir.",
    )


def questions_have_answers_message() -> str:
    return pgettext(
        "exams.service.lifecycle",
        "Seçilmiş suallardan bəzilərinə tələbələrin cavabları və ya apellyasiyaları var. Silinsələr imtahan "
        "nəticələri və tarixçəsi itər. Bunun əvəzinə sualları deaktiv edin — imtahandan çıxarılırlar, amma "
        "cavablar və nəticələr qalır.",
    )


def _locked_exam_and_questions(exam, question_ids):
    exam_model = type(exam)
    locked_exam = exam_model.objects.select_for_update().get(pk=exam.pk)
    question_model = locked_exam.questions.model
    locked_questions = (
        question_model.objects.select_for_update()
        .filter(
            exam_id=locked_exam.pk,
            pk__in=set(question_ids),
        )
        .order_by("pk")
    )
    return locked_exam, locked_questions


def _removes_last_active_questions(locked_exam, affected_questions) -> bool:
    if not locked_exam.is_active or locked_exam.is_deleted:
        return False

    affected_active_ids = list(affected_questions.filter(is_active=True).values_list("pk", flat=True))
    if not affected_active_ids:
        return False
    return not locked_exam.questions.filter(is_active=True).exclude(pk__in=affected_active_ids).exists()


def _guard_delete_history(locked_exam, locked_questions, *, on_used=ON_USED_REFUSE) -> set:
    """Silmə tarixçəni (cavab / apellyasiya) və ya yazılan cəhdi məhv etməsin.

    Qaytarır: istifadə olunmuş (silinə bilməyən) sual ID-ləri — yalnız ``on_used="deactivate"`` olanda
    boş olmaya bilər; ``"refuse"`` rejimində belə suallar varsa ``QuestionsHaveAnswers`` qalxır.
    """
    from apps.exams.services.question_versioning import history_question_ids

    usage_error = exam_in_use_error(locked_exam)
    if usage_error:
        raise ExamInUse(usage_error, code="exam_in_use")
    # Kilidsiz ayrıca sorğu: FOR UPDATE outer join-in nullable tərəfinə tətbiq oluna bilmir.
    question_ids = list(locked_questions.values_list("pk", flat=True))
    used_ids = history_question_ids(question_ids)
    if used_ids and on_used != ON_USED_DEACTIVATE:
        error = QuestionsHaveAnswers(questions_have_answers_message(), code="questions_have_answers")
        error.used_count = len(used_ids)
        error.unused_count = len(question_ids) - len(used_ids)
        raise error
    return used_ids


def log_bulk_question_action(exam, *, verb, count, by_user=None, request=None, extra=None):
    """Toplu sual əməlinin audit sətri (kim, hansı imtahan, əməl, neçə sual, seçim əhatəsi)."""
    from apps.audit.public import log_action
    from core.constants import AuditAction

    changes = {"verb": verb, "count": int(count), "exam_slug": exam.slug}
    changes.update(extra or {})
    return log_action(
        action=AuditAction.DELETE if verb == MODE_DELETE else AuditAction.UPDATE,
        user=by_user,
        organization=exam.organization,
        resource_type=AUDIT_RESOURCE,
        resource_id=str(exam.pk),
        resource_repr=str(exam.title)[:200],
        changes=changes,
        reason=f"exam_questions_{verb}",
        request=request,
    )


def _guard_last_active_questions(exam, locked_exam, affected_questions, *, deactivate_exam, by_user, request):
    """Son aktiv suallar gedirsə: istifadə yoxlaması → təsdiq → imtahanı deaktiv et.

    Qaytarır ``True`` — imtahan bu çağırışda deaktiv edildisə.
    """
    if not _removes_last_active_questions(locked_exam, affected_questions):
        return False

    usage_error = exam_in_use_error(locked_exam)
    if usage_error:
        raise ExamInUse(usage_error, code="exam_in_use")
    if not deactivate_exam:
        raise ActiveExamRequiresQuestion(
            active_exam_question_invariant_message(),
            code="active_exam_requires_question",
        )

    # Mövcud lifecycle keçidi: şərti UPDATE + «exam_unpublished» audit qeydi,
    # bu tranzaksiyanın içində (audit yazılmasa suallar da toxunulmaz qalır).
    return unpublish_exam(exam, by_user=by_user, request=request)


@transaction.atomic
def remove_exam_questions(
    exam,
    question_ids,
    *,
    mode,
    deactivate_exam=False,
    by_user=None,
    request=None,
    on_used=ON_USED_REFUSE,
    audit_extra=None,
) -> QuestionMutationOutcome:
    """Sualları yarışa davamlı sil (``mode="delete"``) və ya deaktiv et (``"deactivate"``).

    ``audit_extra`` verilibsə (toplu əməl) nəticə audit jurnalına yazılır — sual dəyişikliyi ilə EYNİ
    tranzaksiyada (audit yazılmasa suallar da toxunulmaz qalır).
    """
    if mode not in (MODE_DELETE, MODE_DEACTIVATE):
        raise ValueError(f"unknown question mutation mode: {mode!r}")

    locked_exam, locked_questions = _locked_exam_and_questions(exam, question_ids)
    question_count = locked_questions.count()
    used_ids = set()
    if mode == MODE_DELETE:
        # Heç nə dəyişməmişdən ƏVVƏL (imtahanın deaktivasiya təsdiqindən də öncə).
        used_ids = _guard_delete_history(locked_exam, locked_questions, on_used=on_used)
    exam_deactivated = _guard_last_active_questions(
        exam,
        locked_exam,
        locked_questions,
        deactivate_exam=deactivate_exam,
        by_user=by_user,
        request=request,
    )
    if mode == MODE_DELETE:
        deactivated_used = 0
        if used_ids:
            deactivated_used = locked_questions.filter(pk__in=used_ids).update(is_active=False)
            locked_questions.exclude(pk__in=used_ids).delete()
        else:
            locked_questions.delete()
        outcome = QuestionMutationOutcome(
            count=question_count - len(used_ids), exam_deactivated=exam_deactivated, deactivated_used=deactivated_used
        )
    else:
        updated = locked_questions.update(is_active=False)
        outcome = QuestionMutationOutcome(count=updated, exam_deactivated=exam_deactivated)
    if audit_extra is not None and question_count:
        log_bulk_question_action(
            exam,
            verb=mode,
            count=outcome.count,
            by_user=by_user,
            request=request,
            extra={**audit_extra, "kept_used_deactivated": outcome.deactivated_used},
        )
    return outcome


@transaction.atomic
def activate_exam_questions(exam, question_ids, *, by_user=None, request=None, audit_extra=None) -> int:
    """Sualları aktiv et (məlumat silmir); ``audit_extra`` verilibsə audit olunur."""
    _, locked_questions = _locked_exam_and_questions(exam, question_ids)
    updated = locked_questions.filter(is_active=False).update(is_active=True)
    if audit_extra is not None and updated:
        log_bulk_question_action(
            exam, verb="activate", count=updated, by_user=by_user, request=request, extra=audit_extra
        )
    return updated


def delete_exam_questions(exam, question_ids, **kwargs) -> int:
    """Sual ID-lərini yarışa davamlı sil və silinən sual sayını qaytar."""
    return remove_exam_questions(exam, question_ids, mode=MODE_DELETE, **kwargs).count


def deactivate_exam_questions(exam, question_ids, **kwargs) -> int:
    """Sual ID-lərini yarışa davamlı deaktiv et."""
    return remove_exam_questions(exam, question_ids, mode=MODE_DEACTIVATE, **kwargs).count


__all__ = [
    "MODE_DEACTIVATE",
    "MODE_DELETE",
    "ON_USED_DEACTIVATE",
    "ON_USED_REFUSE",
    "AUDIT_RESOURCE",
    "ActiveExamRequiresQuestion",
    "ExamInUse",
    "QuestionMutationOutcome",
    "QuestionsHaveAnswers",
    "activate_exam_questions",
    "active_exam_question_invariant_message",
    "log_bulk_question_action",
    "deactivate_exam_questions",
    "delete_exam_questions",
    "remove_exam_questions",
]
