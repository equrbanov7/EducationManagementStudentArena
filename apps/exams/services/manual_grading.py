"""Atomic manual grading for written/practical exam attempts."""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.exams.services.review_visibility import attempt_review_window_locked


class ManualGradingWindowClosed(Exception):
    """The attempt became immutable before the grading transaction acquired its lock."""


def answer_max_points(answer):
    """Resolve the authoritative grading ceiling from the delivered snapshot."""
    snapshot = getattr(answer, "question_snapshot", None)
    points = snapshot.get("points") if isinstance(snapshot, dict) else None
    if points is None:
        points = getattr(answer.question, "points", 1)
    try:
        return max(1, int(points))
    except (TypeError, ValueError):
        return 1


def _bounded_integer_score(score, *, max_points):
    value = int(Decimal(str(score)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return min(max(0, value), max_points)


def _attempt_score_from_answers(attempt):
    scores = [score for score in attempt.answers.values_list("teacher_score", flat=True) if score is not None]
    return (sum(scores), True) if scores else (None, False)


def _mark_attempt_graded(attempt, *, grader, total_score, checked, now):
    attempt.teacher_score = total_score
    attempt.checked_by_teacher = checked
    update_fields = ["teacher_score", "checked_by_teacher"]
    if checked and not attempt.teacher_checked_at:
        attempt.teacher_checked_at = now
        update_fields.append("teacher_checked_at")
    if attempt.graded_by_id is None and grader is not None:
        attempt.graded_by = grader
        update_fields.append("graded_by")
    attempt.save(update_fields=update_fields)


@transaction.atomic
def apply_single_answer_grade(*, answer_id, score, grader=None, feedback=None, current_time=None):
    """Grade one answer through the same lock/ledger invariant as the UI."""
    from apps.exams.models import ExamAnswer, ExamAttempt, ExamGradeEvent

    attempt_id = ExamAnswer.objects.only("attempt_id").get(pk=answer_id).attempt_id
    attempt = ExamAttempt.objects.select_for_update().get(pk=attempt_id)
    now = current_time or timezone.now()
    if attempt_review_window_locked(attempt, current_time=now):
        raise ManualGradingWindowClosed

    answer = ExamAnswer.objects.select_for_update().select_related("question").get(pk=answer_id)
    max_points = answer_max_points(answer)
    bounded_score = _bounded_integer_score(score, max_points=max_points)
    previous_score = answer.teacher_score
    previous_feedback = answer.teacher_feedback or ""
    next_feedback = previous_feedback if feedback is None else str(feedback)
    if bounded_score == previous_score and next_feedback == previous_feedback:
        return answer

    answer.teacher_score = bounded_score
    answer.teacher_feedback = next_feedback
    answer.save(update_fields=["teacher_score", "teacher_feedback", "updated_at"])
    if bounded_score != previous_score:
        ExamGradeEvent.objects.create(
            attempt=attempt,
            question=answer.question,
            grader=grader,
            old_score=previous_score,
            new_score=bounded_score,
            max_points=max_points,
        )

    total_score, any_score = _attempt_score_from_answers(attempt)
    _mark_attempt_graded(
        attempt,
        grader=grader,
        total_score=total_score,
        checked=any_score or next_feedback != previous_feedback,
        now=now,
    )
    return answer


@transaction.atomic
def apply_attempt_grade(*, attempt_id, score, feedback, grader, max_points=100, current_time=None):
    """Persist a legacy attempt-level manual grade without bypassing the ledger."""
    from apps.exams.models import ExamAttempt, ExamGradeEvent

    now = current_time or timezone.now()
    attempt = ExamAttempt.objects.select_for_update().get(pk=attempt_id)
    if attempt_review_window_locked(attempt, current_time=now):
        raise ManualGradingWindowClosed

    bounded_score = None if score is None else _bounded_integer_score(score, max_points=max_points)
    feedback = (feedback or "").strip()
    previous_score = attempt.teacher_score
    previous_feedback = attempt.teacher_feedback or ""
    if bounded_score == previous_score and feedback == previous_feedback:
        return attempt, False

    if bounded_score != previous_score:
        ExamGradeEvent.objects.create(
            attempt=attempt,
            question=None,
            grader=grader,
            old_score=previous_score,
            new_score=bounded_score,
            max_points=max_points,
        )

    attempt.teacher_feedback = feedback
    _mark_attempt_graded(
        attempt,
        grader=grader,
        total_score=bounded_score,
        checked=bounded_score is not None,
        now=now,
    )
    if feedback != previous_feedback:
        attempt.save(update_fields=["teacher_feedback"])
    return attempt, True


@transaction.atomic
def apply_manual_grading(*, attempt_id, grader, payload, current_time=None):
    """Persist answer grades, their ledger rows and attempt summary atomically.

    The attempt lock serializes concurrent reviewers. Answer rows are locked too,
    so every ledger event observes the score committed by the preceding request.
    A no-op payload does not claim original-grader ownership or start the review
    edit window.
    """
    from apps.exams.models import ExamAttempt, ExamGradeEvent

    now = current_time or timezone.now()
    attempt = ExamAttempt.objects.select_for_update().get(pk=attempt_id)
    if attempt_review_window_locked(attempt, current_time=now):
        raise ManualGradingWindowClosed

    answers = list(attempt.answers.select_for_update().select_related("question").order_by("id"))
    grade_events = []
    grading_changed = False
    total_score = 0
    any_score = False

    for answer in answers:
        question = answer.question
        score_key = f"score_{question.id}"
        feedback_key = f"feedback_{question.id}"
        max_points = answer_max_points(answer)
        previous_score = answer.teacher_score
        previous_feedback = answer.teacher_feedback or ""

        if score_key not in payload:
            score = previous_score
        else:
            score_raw = (payload.get(score_key) or "").strip()
            if score_raw == "":
                score = None
            else:
                try:
                    score = int(score_raw)
                except ValueError:
                    score = 0
                score = min(max(0, score), max_points)

        feedback = (payload.get(feedback_key) or "").strip() if feedback_key in payload else previous_feedback

        if score is not None:
            total_score += score
            any_score = True

        if score == previous_score and feedback == previous_feedback:
            continue

        grading_changed = True
        answer.teacher_score = score
        answer.teacher_feedback = feedback
        answer.save(update_fields=["teacher_score", "teacher_feedback", "updated_at"])

        if score != previous_score:
            grade_events.append(
                ExamGradeEvent(
                    attempt=attempt,
                    question=question,
                    grader=grader,
                    old_score=previous_score,
                    new_score=score,
                    max_points=max_points,
                )
            )

    if grade_events:
        ExamGradeEvent.objects.bulk_create(grade_events)

    if grading_changed:
        attempt.teacher_score = total_score if any_score else None
        attempt.checked_by_teacher = True
        if not attempt.teacher_checked_at:
            attempt.teacher_checked_at = now
        update_fields = ["teacher_score", "checked_by_teacher", "teacher_checked_at"]
        if attempt.graded_by_id is None:
            attempt.graded_by = grader
            update_fields.append("graded_by")
        attempt.save(update_fields=update_fields)

    return attempt, grading_changed


__all__ = [
    "ManualGradingWindowClosed",
    "answer_max_points",
    "apply_attempt_grade",
    "apply_manual_grading",
    "apply_single_answer_grade",
]
