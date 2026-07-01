"""coding_runtime paketi — submission."""

from django.db import transaction

from apps.exams.models import CodingFile, CodingSubmission, ExamAnswer

from .files import (
    get_main_file,
    normalize_files,
)


def create_or_update_draft_submission(*, attempt, coding_question, selected_language, files):
    files = normalize_files(files, coding_question=coding_question)
    main_file = get_main_file(files)
    submission = (
        CodingSubmission.objects.filter(
            student=attempt.user,
            exam=attempt.exam,
            attempt=attempt,
            question=coding_question,
            is_final=False,
        )
        .order_by("-updated_at", "-submitted_at")
        .first()
    )
    if submission is None:
        submission = CodingSubmission.objects.create(
            student=attempt.user,
            exam=attempt.exam,
            attempt=attempt,
            question=coding_question,
            is_final=False,
            selected_language=selected_language,
            submitted_code=main_file["content"] if main_file else "",
            files=files,
            execution_status=CodingSubmission.STATUS_DRAFT,
        )
    submission.selected_language = selected_language
    submission.submitted_code = main_file["content"] if main_file else ""
    submission.files = files
    submission.execution_status = CodingSubmission.STATUS_DRAFT
    submission.save(
        update_fields=[
            "selected_language",
            "submitted_code",
            "files",
            "execution_status",
            "updated_at",
        ]
    )
    sync_submission_files(submission, files)
    return submission


@transaction.atomic
def create_final_submission(*, attempt, coding_question, selected_language, files):
    files = normalize_files(files, coding_question=coding_question)
    main_file = get_main_file(files)
    submission = CodingSubmission.objects.create(
        student=attempt.user,
        exam=attempt.exam,
        attempt=attempt,
        question=coding_question,
        selected_language=selected_language,
        submitted_code=main_file["content"] if main_file else "",
        files=files,
        is_final=True,
        execution_status=CodingSubmission.STATUS_SUBMITTED,
    )
    sync_submission_files(submission, files)
    answer, _ = ExamAnswer.objects.get_or_create(attempt=attempt, question=coding_question.question)
    answer.text_answer = submission.submitted_code
    answer.save(update_fields=["text_answer", "updated_at"])
    return submission


def sync_submission_files(submission, files):
    submission.code_files.all().delete()
    CodingFile.objects.bulk_create(
        [
            CodingFile(
                submission=submission,
                name=item["name"],
                content=item["content"],
                language=item.get("language", ""),
                is_main=bool(item.get("is_main")),
            )
            for item in files
        ]
    )
