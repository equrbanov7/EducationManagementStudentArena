"""Load only the answer data needed to score a page of attempts."""

from django.db.models import Prefetch, prefetch_related_objects

from apps.exams.models import ExamAnswer


def prefetch_result_options(answers, *, for_display=False):
    """Read live options only for answers whose delivered snapshot cannot supply them."""
    legacy_selections = []
    live_questions = []
    for answer in answers:
        if answer.selected_option_ids_snapshot is None:
            legacy_selections.append(answer)
        snapshot = answer.question_snapshot
        if not isinstance(snapshot, dict) or not snapshot.get("options") or (for_display and snapshot.get("v") != 2):
            live_questions.append(answer.question)
    prefetch_related_objects(legacy_selections, "selected_options")
    prefetch_related_objects(live_questions, "options")


def prefetch_score_answers(attempts):
    answers = ExamAnswer.objects.select_related("question").only(
        "attempt_id", "question__points", "question_snapshot", "selected_option_ids_snapshot"
    )
    prefetch_related_objects(attempts, Prefetch("answers", queryset=answers))
    prefetch_result_options(
        answer for attempt in attempts if attempt.exam.exam_type == "test" for answer in attempt.answers.all()
    )
