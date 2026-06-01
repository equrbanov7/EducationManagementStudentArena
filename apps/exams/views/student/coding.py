import io
import json
import re
import zipfile
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET, require_POST

from apps.exams.features import practical_exam_disabled_message, practical_exams_enabled
from apps.exams.models import CodingExamQuestion, CodingSubmission, ExamAttempt
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.coding_definition import ensure_coding_question_for_exam_question
from apps.exams.services.coding_runtime import (
    LANGUAGE_MODES,
    build_starter_files,
    create_final_submission,
    create_or_update_draft_submission,
    execution_language_for_filename,
    grade_files_against_tests,
    mark_file_as_main,
    normalize_files,
    run_visible_code,
)
from apps.exams.services.coding_throttle import acquire_run_slot, release_run_slot
from apps.exams.views.shared.tenant import tenant_scoped_exams

from ._helpers import build_exam_result_url, current_return_to, ensure_student_exam_tenant_context


def _json_error(message, *, status=400, extra=None):
    payload = {"success": False, "error": message}
    if extra:
        payload.update(extra)
    return JsonResponse(payload, status=status)


def _coding_disabled_error():
    return _json_error(practical_exam_disabled_message(), status=403)


def _parse_json_body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return {}


def _get_coding_attempt(request, slug, attempt_id):
    if not practical_exams_enabled():
        raise Http404(practical_exam_disabled_message())
    ensure_student_exam_tenant_context(request)
    return get_object_or_404(
        ExamAttempt.objects.select_related("exam", "user"),
        id=attempt_id,
        exam__in=tenant_scoped_exams(request),
        exam__slug=slug,
        exam__exam_type="coding",
        user=request.user,
    )


def _get_attempt_coding_questions(attempt):
    answers = list(
        attempt.answers.select_related("question", "question__exam", "question__coding_details").order_by("id")
    )
    coding_questions = []
    for answer in answers:
        try:
            coding_question = answer.question.coding_details
        except CodingExamQuestion.DoesNotExist:
            coding_question = ensure_coding_question_for_exam_question(answer.question)
        coding_questions.append(coding_question)
    return coding_questions


def _get_attempt_coding_question(attempt, coding_question_id=None):
    coding_questions = _get_attempt_coding_questions(attempt)
    if not coding_questions:
        return None

    if coding_question_id:
        try:
            coding_question_id = int(coding_question_id)
        except (TypeError, ValueError):
            coding_question_id = None
    if coding_question_id:
        for coding_question in coding_questions:
            if coding_question.id == coding_question_id:
                return coding_question
        return None

    return coding_questions[0]


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


def _safe_archive_name(name, used_names):
    clean = str(name or "").replace("\\", "/").split("/")[-1].strip()
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", clean).strip("._") or "file.txt"
    candidate = clean
    stem, dot, suffix = clean.partition(".")
    counter = 2
    while candidate in used_names:
        candidate = f"{stem}_{counter}{dot}{suffix}" if dot else f"{stem}_{counter}"
        counter += 1
    used_names.add(candidate)
    return candidate


def _submission_file_items(submission):
    code_files = list(submission.code_files.all())
    if code_files:
        return [
            {
                "name": code_file.name,
                "content": code_file.content or "",
            }
            for code_file in code_files
        ]
    return [
        {
            "name": item.get("name") or "file.txt",
            "content": item.get("content") or "",
        }
        for item in (submission.files or [])
        if isinstance(item, dict)
    ]


def _get_submission_download_attempt(request, slug, attempt_id):
    if not practical_exams_enabled():
        raise Http404(practical_exam_disabled_message())
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("exam", "user"),
        id=attempt_id,
        exam__slug=slug,
        exam__exam_type="coding",
    )
    if attempt.user_id == request.user.id:
        ensure_student_exam_tenant_context(request)
        if tenant_scoped_exams(request).filter(id=attempt.exam_id).exists():
            return attempt
        raise PermissionDenied

    _ensure_teacher(request.user)
    if tenant_scoped_exams(request).filter(id=attempt.exam_id).exists():
        return attempt
    raise PermissionDenied


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


def _latest_draft_submissions_by_question(*, student, exam, attempt, coding_questions):
    question_ids = [coding_question.id for coding_question in coding_questions]
    submissions = CodingSubmission.objects.filter(
        student=student,
        exam=exam,
        attempt=attempt,
        question_id__in=question_ids,
        is_final=False,
    ).order_by("question_id", "-updated_at")
    latest = {}
    for submission in submissions:
        latest.setdefault(submission.question_id, submission)
    return latest


def _serialize_coding_question(coding_question, *, index, latest_submission):
    initial_files = latest_submission.files if latest_submission else build_starter_files(coding_question)
    initial_files = normalize_files(initial_files, coding_question=coding_question)
    return {
        "id": coding_question.id,
        "base_question_id": coding_question.question_id,
        "number": index,
        "title": coding_question.title,
        "problem_statement": coding_question.problem_statement,
        "input_description": coding_question.input_description,
        "output_description": coding_question.output_description,
        "example_input": coding_question.example_input,
        "example_output": coding_question.example_output,
        "language": coding_question.language,
        "language_display": str(coding_question.get_language_display()),
        "max_score": coding_question.max_score,
        "time_limit_seconds": coding_question.time_limit_seconds,
        "memory_limit_mb": coding_question.memory_limit_mb,
        "initial_files": initial_files,
        "starter_files": build_starter_files(coding_question),
        "visible_test_cases": _serialize_visible_test_cases(coding_question),
        "selected_language": latest_submission.selected_language if latest_submission else coding_question.language,
        "latest_submission": _submission_payload(latest_submission),
    }


def take_coding_exam(request, *, exam, attempt, remaining_seconds, history_url, previous_attempts, supervision):
    if not practical_exams_enabled():
        raise Http404(practical_exam_disabled_message())

    coding_questions = _get_attempt_coding_questions(attempt)
    if not coding_questions:
        return _json_error(pgettext("exams.view.coding.error", "coding_question_not_found"), status=404)

    latest_submissions = _latest_draft_submissions_by_question(
        student=request.user,
        exam=exam,
        attempt=attempt,
        coding_questions=coding_questions,
    )
    serialized_questions = [
        _serialize_coding_question(
            coding_question,
            index=index,
            latest_submission=latest_submissions.get(coding_question.id),
        )
        for index, coding_question in enumerate(coding_questions, start=1)
    ]
    coding_question = coding_questions[0]
    first_question_payload = serialized_questions[0]

    context = {
        "exam": exam,
        "attempt": attempt,
        "coding_question": coding_question,
        "coding_questions": serialized_questions,
        "coding_languages": CodingExamQuestion.LANGUAGE_CHOICES,
        "language_modes": LANGUAGE_MODES,
        "initial_files": first_question_payload["initial_files"],
        "starter_files": first_question_payload["starter_files"],
        "latest_submission": latest_submissions.get(coding_question.id),
        "visible_test_cases": first_question_payload["visible_test_cases"],
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


@login_required
@require_GET
def coding_submission_download(request, slug, attempt_id, submission_id):
    attempt = _get_submission_download_attempt(request, slug, attempt_id)
    submission = get_object_or_404(
        CodingSubmission.objects.prefetch_related("code_files").select_related("question", "question__question"),
        id=submission_id,
        attempt=attempt,
        is_final=True,
    )
    file_items = _submission_file_items(submission)
    if not file_items:
        raise Http404(pgettext("exams.view.coding.error", "coding_submission_files_not_found"))

    archive_buffer = io.BytesIO()
    used_names = set()
    with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_item in file_items:
            archive.writestr(
                _safe_archive_name(file_item["name"], used_names),
                file_item["content"],
            )

    question_number = getattr(getattr(submission.question, "question", None), "order", submission.question_id)
    filename = f"{attempt.exam.slug}-attempt-{attempt.id}-question-{question_number}.zip"
    response = HttpResponse(archive_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _build_submission_input(request, attempt):
    data = _parse_json_body(request)
    coding_question = _get_attempt_coding_question(attempt, data.get("question_id"))
    if coding_question is None:
        return (
            None,
            None,
            None,
            _json_error(pgettext("exams.view.coding.error", "coding_question_not_found"), status=404),
        )

    allowed_languages = {value for value, _ in CodingExamQuestion.LANGUAGE_CHOICES}
    active_file_name = data.get("active_file_name") or ""
    selected_language = data.get("selected_language") or coding_question.language
    if selected_language not in allowed_languages:
        selected_language = coding_question.language

    files = normalize_files(data.get("files") or [], coding_question=coding_question)
    if active_file_name:
        selected_language = execution_language_for_filename(active_file_name, selected_language)
        files = mark_file_as_main(files, active_file_name)
    stdin = data.get("stdin") or ""
    return coding_question, selected_language, {"files": files, "stdin": stdin}, None


def _build_submission_items(request, attempt):
    data = _parse_json_body(request)
    raw_items = data.get("questions")
    if not isinstance(raw_items, list):
        coding_question, selected_language, payload, error = _build_submission_input(request, attempt)
        if error:
            return None, error
        return [
            {
                "coding_question": coding_question,
                "selected_language": selected_language,
                "files": payload["files"],
                "stdin": payload["stdin"],
            }
        ], None

    allowed_languages = {value for value, _ in CodingExamQuestion.LANGUAGE_CHOICES}
    items = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        coding_question = _get_attempt_coding_question(attempt, raw_item.get("question_id"))
        if coding_question is None:
            return None, _json_error(pgettext("exams.view.coding.error", "coding_question_not_found"), status=404)
        active_file_name = raw_item.get("active_file_name") or ""
        selected_language = raw_item.get("selected_language") or coding_question.language
        if selected_language not in allowed_languages:
            selected_language = coding_question.language
        files = normalize_files(raw_item.get("files") or [], coding_question=coding_question)
        if active_file_name:
            selected_language = execution_language_for_filename(active_file_name, selected_language)
            files = mark_file_as_main(files, active_file_name)
        items.append(
            {
                "coding_question": coding_question,
                "selected_language": selected_language,
                "files": files,
                "stdin": raw_item.get("stdin") or "",
            }
        )

    if not items:
        return None, _json_error(pgettext("exams.view.coding.error", "coding_question_not_found"), status=404)
    return items, None


@login_required
@require_POST
def coding_autosave(request, slug, attempt_id):
    if not practical_exams_enabled():
        return _coding_disabled_error()
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
    if not practical_exams_enabled():
        return _coding_disabled_error()
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

    # Reserve a per-user run slot before we touch the executor. This bounds
    # how many concurrent runs a single student can have in flight and
    # protects the executor pool when a full classroom (100+ students)
    # presses Run at the same instant. The slot is released in a finally
    # block so a crashed run doesn't leak the reservation.
    decision = acquire_run_slot(user_id=request.user.id)
    if not decision.allowed:
        if decision.reason == "rate_limited":
            message = pgettext(
                "exams.view.coding.error",
                "You are running code too quickly. Please wait a moment and try again.",
            )
        else:
            message = pgettext(
                "exams.view.coding.error",
                "You already have a code run in progress. Wait for it to finish.",
            )
        response = _json_error(message, status=429, extra={"retry_after_seconds": decision.retry_after_seconds})
        response["Retry-After"] = str(decision.retry_after_seconds or 1)
        return response

    submission = create_or_update_draft_submission(
        attempt=attempt,
        coding_question=coding_question,
        selected_language=selected_language,
        files=payload["files"],
    )
    try:
        result = run_visible_code(
            coding_question=coding_question,
            selected_language=selected_language,
            files=payload["files"],
            stdin=payload["stdin"],
        )
    finally:
        release_run_slot(decision.slot_token)
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
    if not practical_exams_enabled():
        return _coding_disabled_error()
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

    submission_items, error = _build_submission_items(request, attempt)
    if error:
        return error

    submissions = []
    total_score = Decimal("0")
    total_passed = 0
    total_failed = 0
    all_scored = True

    for item in submission_items:
        coding_question = item["coding_question"]
        submission = create_final_submission(
            attempt=attempt,
            coding_question=coding_question,
            selected_language=item["selected_language"],
            files=item["files"],
        )

        result = grade_files_against_tests(
            coding_question=coding_question,
            selected_language=item["selected_language"],
            files=item["files"],
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
            total_score += Decimal(submission.score)
            passed = sum(1 for case in result["test_results"] if case.get("passed"))
            failed = max(len(result["test_results"]) - passed, 0)
            total_passed += passed
            total_failed += failed
        else:
            all_scored = False

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
        submissions.append(submission)

    if all_scored and submissions:
        attempt.correct_count = total_passed
        attempt.wrong_count = total_failed
        attempt.teacher_score = int(total_score)
        attempt.checked_by_teacher = True
        if not attempt.teacher_checked_at:
            attempt.teacher_checked_at = timezone.now()
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
            "submission": _submission_payload(submissions[0] if submissions else None),
            "submissions": [_submission_payload(submission) for submission in submissions],
            "redirect_url": build_exam_result_url(attempt, return_to=current_return_to(request)),
        }
    )
