from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.exams.models import ExamAnswer


def calculate_attempt_score(attempt):
    total_score = Decimal("0")
    for answer in attempt.answers.select_related("question"):
        if answer.teacher_score is not None:
            total_score += Decimal(str(answer.teacher_score))
        elif answer.question.exam.exam_type == "test" and answer.is_correct:
            total_score += Decimal(str(answer.question.points))
    return total_score


@transaction.atomic
def grade_exam_answer(answer, score, graded_by=None, feedback=None):
    if isinstance(score, str):
        score = Decimal(score)
    answer.teacher_score = int(Decimal(score))
    if feedback is not None:
        answer.teacher_feedback = feedback
        answer.save(update_fields=["teacher_score", "teacher_feedback"])
    else:
        answer.save(update_fields=["teacher_score"])
    return answer


@transaction.atomic
def bulk_grade_answers(answer_ids, scores, graded_by=None):
    answers = ExamAnswer.objects.filter(id__in=answer_ids)
    count = 0
    for answer, score in zip(answers, scores):
        grade_exam_answer(answer, score, graded_by)
        count += 1
    return count


def parse_score_value(value, *, default=None):
    if value in (None, ""):
        return default

    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return default


__all__ = [
    "bulk_grade_answers",
    "calculate_attempt_score",
    "grade_exam_answer",
    "parse_score_value",
]
