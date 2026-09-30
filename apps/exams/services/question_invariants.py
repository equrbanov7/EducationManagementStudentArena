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
"""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
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


@dataclass(frozen=True)
class QuestionMutationOutcome:
    count: int
    exam_deactivated: bool = False


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


def _guard_delete_history(locked_exam, locked_questions):
    """Silmə tarixçəni (cavab / apellyasiya) və ya yazılan cəhdi məhv etməsin."""
    usage_error = exam_in_use_error(locked_exam)
    if usage_error:
        raise ExamInUse(usage_error, code="exam_in_use")
    # Kilidsiz ayrıca sorğu: FOR UPDATE outer join-in nullable tərəfinə tətbiq oluna bilmir.
    question_ids = list(locked_questions.values_list("pk", flat=True))
    with_history = locked_questions.model.objects.filter(pk__in=question_ids).filter(
        Q(answers__isnull=False) | Q(appeal_items__isnull=False)
    )
    if with_history.exists():
        raise QuestionsHaveAnswers(questions_have_answers_message(), code="questions_have_answers")


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
    exam, question_ids, *, mode, deactivate_exam=False, by_user=None, request=None
) -> QuestionMutationOutcome:
    """Sualları yarışa davamlı sil (``mode="delete"``) və ya deaktiv et (``"deactivate"``)."""
    if mode not in (MODE_DELETE, MODE_DEACTIVATE):
        raise ValueError(f"unknown question mutation mode: {mode!r}")

    locked_exam, locked_questions = _locked_exam_and_questions(exam, question_ids)
    question_count = locked_questions.count()
    if mode == MODE_DELETE:
        # Heç nə dəyişməmişdən ƏVVƏL (imtahanın deaktivasiya təsdiqindən də öncə).
        _guard_delete_history(locked_exam, locked_questions)
    exam_deactivated = _guard_last_active_questions(
        exam,
        locked_exam,
        locked_questions,
        deactivate_exam=deactivate_exam,
        by_user=by_user,
        request=request,
    )
    if mode == MODE_DELETE:
        locked_questions.delete()
        return QuestionMutationOutcome(count=question_count, exam_deactivated=exam_deactivated)
    updated = locked_questions.update(is_active=False)
    return QuestionMutationOutcome(count=updated, exam_deactivated=exam_deactivated)


def delete_exam_questions(exam, question_ids, **kwargs) -> int:
    """Sual ID-lərini yarışa davamlı sil və silinən sual sayını qaytar."""
    return remove_exam_questions(exam, question_ids, mode=MODE_DELETE, **kwargs).count


def deactivate_exam_questions(exam, question_ids, **kwargs) -> int:
    """Sual ID-lərini yarışa davamlı deaktiv et."""
    return remove_exam_questions(exam, question_ids, mode=MODE_DEACTIVATE, **kwargs).count


__all__ = [
    "MODE_DEACTIVATE",
    "MODE_DELETE",
    "ActiveExamRequiresQuestion",
    "ExamInUse",
    "QuestionMutationOutcome",
    "QuestionsHaveAnswers",
    "active_exam_question_invariant_message",
    "deactivate_exam_questions",
    "delete_exam_questions",
    "remove_exam_questions",
]
