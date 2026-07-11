from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.task_submission_core.public import parse_score_value


def parse_decimal_input(raw_value):
    raw_value = (str(raw_value).strip() if raw_value is not None else "").replace(",", ".")
    if not raw_value:
        return None
    try:
        return Decimal(raw_value)
    except (InvalidOperation, TypeError, ValueError):
        return None


def format_decimal_input(value):
    if value is None or value == "":
        return ""

    formatted = format(Decimal(str(value)), "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")

    return formatted or "0"


def _clamp_decimal_score(value, maximum):
    """Return a score inside ``[0, maximum]`` using exact Decimal math."""
    if value is None:
        return None
    parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    parsed = max(parsed, Decimal("0"))
    if maximum is None:
        return parsed
    ceiling = max(Decimal(str(maximum)), Decimal("0"))
    return min(parsed, ceiling)


def _lock_instance(instance, *related_fields):
    """Re-read a persisted grading target with a transaction row lock."""
    manager = getattr(type(instance), "_default_manager", None)
    pk = getattr(instance, "pk", None)
    if manager is None or pk is None:
        return instance
    queryset = manager.select_for_update()
    if related_fields:
        queryset = queryset.select_related(*related_fields)
    return queryset.get(pk=pk)


@transaction.atomic
def grade_lab_submission(submission, score, feedback, graded_by, *, refresh_graded_at=True):
    submission = _lock_instance(submission, "assignment__lab")
    score = _clamp_decimal_score(score, submission.assignment.lab.max_score)

    submission.score = score
    submission.feedback = feedback
    submission.graded_by = graded_by
    if refresh_graded_at or not submission.graded_at:
        submission.graded_at = timezone.now()
    submission.status = "graded"
    submission.save(update_fields=["score", "feedback", "graded_by", "graded_at", "status", "updated_at"])

    return submission


@transaction.atomic
def grade_lab_answer(answer, score, feedback=None):
    answer = _lock_instance(answer, "question")
    score = _clamp_decimal_score(score, answer.question.points)

    answer.score = score
    answer.save(update_fields=["score", "submitted_at"])
    return answer


def calculate_lab_total_score(assignment):
    answers = assignment.answers.all()
    total_score = Decimal("0")

    for answer in answers:
        if answer.score is not None:
            total_score += answer.score

    submission = assignment.submissions.filter(status="graded").first()
    if submission and submission.score:
        total_score += submission.score

    return total_score


__all__ = [
    "calculate_lab_total_score",
    "format_decimal_input",
    "grade_lab_answer",
    "grade_lab_submission",
    "parse_decimal_input",
    "parse_score_value",
]
