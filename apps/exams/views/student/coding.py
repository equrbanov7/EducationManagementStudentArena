import json
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.exams.models import CodingExamQuestion, CodingSubmission, ExamAnswer, ExamAttempt
from apps.exams.services.coding_runtime import (
    LANGUAGE_MODES,
    build_starter_files,
    create_final_submission,
    create_or_update_draft_submission,
    get_first_coding_question,
    grade_files_against_tests,
    normalize_files,
    run_visible_code,
)
from apps.exams.views.shared.tenant import tenant_scoped_exams

from ._helpers import build_exam_result_url, current_return_to, ensure_student_exam_tenant_context


def _json_error(message, *, status=400, extra=None):
    payload = {"success": False, "error": message}
    if extra:
        payload.update(extra)
    return JsonResponse(payload, status=status)


def _parse_json_body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return {}


def _get_coding_attempt(request, slug, attempt_id):
    ensure_student_exam_tenant_context(request)
    return get_object_or_404(
        ExamAttempt.objects.select_related("exam", "user"),
        id=attempt_id,
        exam__in=tenant_scoped_exams(request),
        exam__slug=slug,
        exam__exam_type="coding",
        user=request.user,
    )


def _get_attempt_coding_question(attempt):
    answer = (
        attempt.answers.select_related("question", "question__coding_details")
        .filter(question__coding_details__isnull=False)
        .order_by("id")
        .first()
    )
    if answer:
        return answer.question.coding_details
    coding_question = get_first_coding_question(attempt.exam)
    if coding_question:
        ExamAnswer.objects.get_or_create(attempt=attempt, question=coding_question.question)
    return coding_question


def _submission_payload(submission):
    if not submission:
        return None
    return {
        "id": submission.id,
        "status": submission.execution_status,
        "output": submission.output,
        "error": submission.error_message,
        "score": float(submission.score) if submission.score is not None else None,
        "test_results": submission.test_results,
        "execution_time_ms": submission.execution_time_ms,
        "memory_usage_kb": submission.memory_usage_kb,
        "is_final": submission.is_final,
    }


def _serialize_visible_test_cases(coding_question):
    return [
        {
            "id": case.id,
            "input": case.input_data,
            "expected": case.expected_output,
            "points": case.point_value,
        }
        for case in coding_question.test_cases.filter(visibility="visible").order_by("order", "id")
    ]


def take_coding_exam(request, *, exam, attempt, remaining_seconds, history_url, previous_attempts, supervision):
    coding_question = _get_attempt_coding_question(attempt)
    if coding_question is None:
        return _json_error(pgettext("exams.view.coding.error", "coding_question_not_found"), status=404)

    latest_submission = (
        CodingSubmission.objects.filter(
            student=request.user,
            exam=exam,
            attempt=attempt,
            question=coding_question,
            is_final=False,
        )
        .order_by("-updated_at")
        .first()
    )
    initial_files = latest_submission.files if latest_submission else build_starter_files(coding_question)
    initial_files = normalize_files(initial_files, coding_question=coding_question)

    context = {
        "exam": exam,
        "attempt": attempt,
        "coding_question": coding_question,
        "coding_languages": CodingExamQuestion.LANGUAGE_CHOICES,
        "language_modes": LANGUAGE_MODES,
        "initial_files": initial_files,
        "starter_files": build_starter_files(coding_question),
        "latest_submission": latest_submission,
        "visible_test_cases": _serialize_visible_test_cases(coding_question),
        "remaining_seconds": remaining_seconds,
        "history_url": history_url,
        "previous_attempts": previous_attempts,
        "previous_attempts_count": len(previous_attempts),
        "supervision": supervision,
        "autosave_url": reverse("exams:coding_autosave", kwargs={"slug": exam.slug, "attempt_id": attempt.id}),
        "run_url": reverse("exams:coding_run", kwargs={"slug": exam.slug, "attempt_id": attempt.id}),
        "submit_url": reverse("exams:coding_submit", kwargs={"slug": exam.slug, "attempt_id": attempt.id}),
        "result_url": build_exam_result_url(attempt, return_to=current_return_to(request)),
    }
    return render(request, "exams/student/take_coding_exam.html", context)


def _build_submission_input(request, attempt):
    data = _parse_json_body(request)
    coding_question = _get_attempt_coding_question(attempt)
    if coding_question is None:
        return (
            None,
            None,
            None,
            _json_error(pgettext("exams.view.coding.error", "coding_question_not_found"), status=404),
        )

    allowed_languages = {value for value, _ in CodingExamQuestion.LANGUAGE_CHOICES}
    selected_language = data.get("selected_language") or coding_question.language
    if selected_language not in allowed_languages:
        selected_language = coding_question.language

    files = normalize_files(data.get("files") or [], coding_question=coding_question)
    stdin = data.get("stdin") or ""
    return coding_question, selected_language, {"files": files, "stdin": stdin}, None


@login_required
@require_POST
def coding_autosave(request, slug, attempt_id):
    attempt = _get_coding_attempt(request, slug, attempt_id)
    if attempt.is_finished or attempt.expire_if_time_limit_reached():
        return _json_error(
            pgettext("exams.view.coding.error", "attempt_already_finished"),
            status=409,
            extra={
                "finished": True,
                "redirect_url": build_exam_result_url(attempt, return_to=current_return_to(request)),
            },
        )

    coding_question, selected_language, payload, error = _build_submission_input(request, attempt)
    if error:
        return error

    submission = create_or_update_draft_submission(
        attempt=attempt,
        coding_question=coding_question,
        selected_language=selected_language,
        files=payload["files"],
    )
    if attempt.status != "draft":
        attempt.status = "draft"
        attempt.save(update_fields=["status"])
    return JsonResponse({"success": True, "submission": _submission_payload(submission)})


@login_required
@require_POST
def coding_run(request, slug, attempt_id):
    attempt = _get_coding_attempt(request, slug, attempt_id)
    if attempt.is_finished or attempt.expire_if_time_limit_reached():
        return _json_error(
            pgettext("exams.view.coding.error", "attempt_already_finished"),
            status=409,
            extra={
                "finished": True,
                "redirect_url": build_exam_result_url(attempt, return_to=current_return_to(request)),
            },
        )

    coding_question, selected_language, payload, error = _build_submission_input(request, attempt)
    if error:
        return error

    submission = create_or_update_draft_submission(
        attempt=attempt,
        coding_question=coding_question,
        selected_language=selected_language,
        files=payload["files"],
    )
    result = run_visible_code(
        coding_question=coding_question,
        selected_language=selected_language,
        files=payload["files"],
        stdin=payload["stdin"],
    )
    submission.execution_status = result["status"]
    submission.output = result["output"]
    submission.error_message = result["error"]
    submission.test_results = result["test_results"]
    submission.score = result["score"]
    submission.execution_time_ms = result["execution_time_ms"]
    submission.memory_usage_kb = result["memory_usage_kb"]
    submission.save(
        update_fields=[
            "execution_status",
            "output",
            "error_message",
            "test_results",
            "score",
            "execution_time_ms",
            "memory_usage_kb",
            "updated_at",
        ]
    )
    return JsonResponse({"success": True, "submission": _submission_payload(submission)})


@login_required
@require_POST
def coding_submit(request, slug, attempt_id):
    attempt = _get_coding_attempt(request, slug, attempt_id)
    already_finished = attempt.is_finished
    time_expired = attempt.is_time_limit_reached()

    if already_finished:
        return JsonResponse(
            {
                "success": True,
                "finished": True,
                "redirect_url": build_exam_result_url(attempt, return_to=current_return_to(request)),
            }
        )

    coding_question, selected_language, payload, error = _build_submission_input(request, attempt)
    if error:
        return error

    submission = create_final_submission(
        attempt=attempt,
        coding_question=coding_question,
        selected_language=selected_language,
        files=payload["files"],
    )

    result = grade_files_against_tests(
        coding_question=coding_question,
        selected_language=selected_language,
        files=payload["files"],
        include_hidden=True,
    )
    submission.execution_status = (
        result["status"] if coding_question.enable_code_execution else CodingSubmission.STATUS_SUBMITTED
    )
    submission.output = result["output"]
    submission.error_message = result["error"]
    submission.test_results = result["test_results"]
    submission.execution_time_ms = result["execution_time_ms"]
    submission.memory_usage_kb = result["memory_usage_kb"]

    if result["score"] is not None:
        submission.score = min(Decimal(result["score"]), Decimal(coding_question.max_score))
        passed = sum(1 for item in result["test_results"] if item.get("passed"))
        failed = max(len(result["test_results"]) - passed, 0)
        attempt.correct_count = passed
        attempt.wrong_count = failed
        attempt.teacher_score = int(submission.score)
        attempt.checked_by_teacher = True
        if not attempt.teacher_checked_at:
            attempt.teacher_checked_at = timezone.now()

    submission.save(
        update_fields=[
            "execution_status",
            "output",
            "error_message",
            "test_results",
            "score",
            "execution_time_ms",
            "memory_usage_kb",
            "updated_at",
        ]
    )
    attempt.mark_finished(
        status="expired" if time_expired else "submitted",
        extra_update_fields=[
            "correct_count",
            "wrong_count",
            "teacher_score",
            "checked_by_teacher",
            "teacher_checked_at",
        ],
    )

    return JsonResponse(
        {
            "success": True,
            "finished": True,
            "submission": _submission_payload(submission),
            "redirect_url": build_exam_result_url(attempt, return_to=current_return_to(request)),
        }
    )
