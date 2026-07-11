from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction

from apps.exams.models import ExamAnswer
from apps.exams.services.manual_grading import apply_single_answer_grade


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
    # teacher_score PositiveIntegerField-dir (qiymətləndirmə sistemi qəsdən
    # integer-əsaslıdır). Səssiz kəsmə (int() truncation) əvəzinə ən yaxına
    # yuvarlaqlaşdırırıq və mənfi dəyərləri 0-a sıxırıq — live_exam.scoring
    # ilə eyni davranış.
    normalized_score = max(0, int(Decimal(score).quantize(Decimal("1"), rounding=ROUND_HALF_UP)))
    persisted = apply_single_answer_grade(
        answer_id=answer.pk,
        score=normalized_score,
        grader=graded_by,
        feedback=feedback,
    )
    # Preserve the historical API contract: callers receive the same model
    # instance they passed in, now synchronized with the locked DB row.
    answer.teacher_score = persisted.teacher_score
    answer.teacher_feedback = persisted.teacher_feedback
    return answer


@transaction.atomic
def bulk_grade_answers(answer_ids, scores, graded_by=None):
    # answer_ids və scores eyni indeks üzrə uyğunlaşdırılır. ÖNCƏ id→score
    # xəritəsi qururuq: `filter(id__in=...)` qaytardığı sıra answer_ids-in
    # sırasına ZƏMANƏTLİ deyil (ORDER BY yoxdur), ona görə birbaşa zip() ballarla
    # səhv cavabları cütləşdirə bilərdi. Xəritə ilə hər balı düzgün cavaba
    # bağlayırıq.
    score_by_id = dict(zip(answer_ids, scores))
    answers = ExamAnswer.objects.filter(id__in=answer_ids)
    count = 0
    for answer in answers:
        if answer.id not in score_by_id:
            continue
        grade_exam_answer(answer, score_by_id[answer.id], graded_by)
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
