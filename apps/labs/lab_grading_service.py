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


@transaction.atomic
def grade_lab_submission(submission, score, feedback, graded_by, *, refresh_graded_at=True):
    if isinstance(score, str):
        score = Decimal(score)

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
    if isinstance(score, str):
        score = Decimal(score)

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
