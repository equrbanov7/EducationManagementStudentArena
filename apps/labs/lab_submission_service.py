from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from .models import LabAnswer, LabSubmission


def get_next_attempt_number(assignment):
    if assignment is None:
        return 1

    latest_submission = assignment.submissions.order_by("-attempt_number", "-submitted_at").first()
    if latest_submission is not None and latest_submission.attempt_number:
        return latest_submission.attempt_number + 1

    return assignment.submissions.count() + 1


def is_lab_open(lab, *, current_time=None):
    now = current_time or timezone.now()

    if lab.start_datetime and lab.end_datetime:
        return lab.status == "published" and lab.start_datetime <= now <= lab.end_datetime

    return lab.status == "published"


def format_lab_submission_duration(start_time, submitted_at):
    if not start_time or not submitted_at:
        return None

    delta = submitted_at - start_time
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return None

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if hours > 0:
        duration_tpl = pgettext("labs.view.message", "duration_hours_minutes")
        try:
            return duration_tpl % {"hours": hours, "minutes": minutes}
        except Exception:
            return duration_tpl.format(hours=hours, minutes=minutes)

    duration_tpl = pgettext("labs.view.message", "duration_minutes")
    try:
        return duration_tpl % {"minutes": minutes}
    except Exception:
        return duration_tpl.format(minutes=minutes)


@transaction.atomic
def create_lab_submission(
    assignment,
    uploaded_file=None,
    *,
    attempt_number=None,
    submission_text="",
    submission_link="",
    status="submitted",
):
    submission = LabSubmission.objects.create(
        assignment=assignment,
        submitted_at=timezone.now(),
        attempt_number=attempt_number or get_next_attempt_number(assignment),
        submission_text=submission_text,
        submission_link=submission_link,
        status=status,
    )

    if uploaded_file:
        submission.submission_file = uploaded_file
        submission.save(update_fields=["submission_file", "updated_at"])

    return submission


@transaction.atomic
def update_lab_submission(submission, uploaded_file=None):
    update_fields = ["submitted_at", "status", "updated_at"]

    if uploaded_file:
        submission.submission_file = uploaded_file
        update_fields.append("submission_file")

    submission.submitted_at = timezone.now()
    submission.status = "submitted"
    submission.save(update_fields=update_fields)

    return submission


@transaction.atomic
def auto_save_lab_answers(assignment, answers_data):
    count = 0
    attempt_number = get_next_attempt_number(assignment)

    for question_id, answer_text in answers_data.items():
        LabAnswer.objects.update_or_create(
            lab=assignment.lab,
            question_id=question_id,
            student=assignment.student,
            attempt_number=attempt_number,
            defaults={
                "submission": None,
                "answer": answer_text,
                "is_draft": True,
            },
        )
        count += 1

    return count


@transaction.atomic
def finalize_submission_answers(submission):
    return LabAnswer.objects.filter(
        lab=submission.assignment.lab,
        student=submission.assignment.student,
        attempt_number=submission.attempt_number,
        is_draft=True,
    ).update(is_draft=False, submission=submission)


__all__ = [
    "auto_save_lab_answers",
    "create_lab_submission",
    "finalize_submission_answers",
    "format_lab_submission_duration",
    "get_next_attempt_number",
    "is_lab_open",
    "update_lab_submission",
]
