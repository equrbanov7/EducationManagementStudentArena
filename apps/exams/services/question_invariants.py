"""Aktiv imtahanın publish qapısını sual mutasiyalarında qoruyur."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import pgettext


def active_exam_question_invariant_message() -> str:
    return pgettext(
        "exams.service.lifecycle",
        "Aktiv imtahanın son aktiv sualı silinə və ya deaktiv edilə bilməz. Əvvəl imtahanı deaktiv edin.",
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


def _ensure_active_question_remains(locked_exam, affected_questions) -> None:
    if not locked_exam.is_active or locked_exam.is_deleted:
        return

    affected_active_ids = list(affected_questions.filter(is_active=True).values_list("pk", flat=True))
    if not affected_active_ids:
        return
    if locked_exam.questions.filter(is_active=True).exclude(pk__in=affected_active_ids).exists():
        return
    raise ValidationError(active_exam_question_invariant_message(), code="active_exam_requires_question")


@transaction.atomic
def delete_exam_questions(exam, question_ids) -> int:
    """Sual ID-lərini yarışa davamlı sil və silinən sual sayını qaytar."""
    locked_exam, locked_questions = _locked_exam_and_questions(exam, question_ids)
    question_count = locked_questions.count()
    _ensure_active_question_remains(locked_exam, locked_questions)
    locked_questions.delete()
    return question_count


@transaction.atomic
def deactivate_exam_questions(exam, question_ids) -> int:
    """Sual ID-lərini yarışa davamlı deaktiv et."""
    locked_exam, locked_questions = _locked_exam_and_questions(exam, question_ids)
    _ensure_active_question_remains(locked_exam, locked_questions)
    return locked_questions.update(is_active=False)


__all__ = [
    "active_exam_question_invariant_message",
    "deactivate_exam_questions",
    "delete_exam_questions",
]
