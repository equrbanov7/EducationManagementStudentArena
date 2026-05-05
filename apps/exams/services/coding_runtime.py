import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction

from apps.exams.models import CodingExamQuestion, CodingFile, CodingSubmission, CodingTestCase, ExamAnswer

MAX_CODE_BYTES = 256_000
MAX_CAPTURE_BYTES = 64_000
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,180}$")


LANGUAGE_MODES = {
    "javascript": "javascript",
    "python": "python",
    "cpp": "text/x-c++src",
    "java": "text/x-java",
    "html": "htmlmixed",
    "css": "css",
}


DOCKER_IMAGES = {
    "javascript": "node:22-alpine",
    "python": "python:3.12-alpine",
    "cpp": "gcc:14",
    "java": "eclipse-temurin:21",
}

# Secure execution plan:
# - Never run submitted code in the Django process; this service only dispatches
#   to Docker with no network, memory/CPU limits, PID limits, read-only root,
#   and a server-side timeout.
# - Production TODO: move Docker execution into a dedicated worker host or
#   orchestrated sandbox pool with image pre-pulling, per-tenant quotas, audit
#   logs, and stronger kernel isolation such as gVisor/Kata if available.


@dataclass
class ExecutionResult:
    status: str
    output: str = ""
    error: str = ""
    execution_time_ms: int | None = None
    memory_usage_kb: int | None = None


def get_first_coding_question(exam):
    return (
        CodingExamQuestion.objects.filter(question__exam=exam, question__is_active=True)
        .select_related("question", "question__exam")
        .prefetch_related("test_cases")
        .order_by("question__order", "id")
        .first()
    )


def file_language_for_name(filename, fallback_language):
    suffix = Path(filename).suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix == ".js":
        return "javascript"
    if suffix in {".cpp", ".cc", ".cxx", ".hpp", ".h"}:
        return "cpp"
    if suffix == ".java":
        return "java"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".css":
        return "css"
    return fallback_language


def build_starter_files(coding_question):
    language = coding_question.language
    starter_code = coding_question.starter_code or ""
    if language == CodingExamQuestion.LANGUAGE_HTML:
        return [
            {
                "name": "index.html",
                "content": starter_code or "<!doctype html>\n<html>\n<body>\n\n</body>\n</html>\n",
                "language": "html",
                "is_main": True,
            },
            {"name": "style.css", "content": "", "language": "css", "is_main": False},
            {"name": "script.js", "content": "", "language": "javascript", "is_main": False},
        ]

    filename = coding_question.default_filename
    return [
        {
            "name": filename,
            "content": starter_code,
            "language": file_language_for_name(filename, language),
            "is_main": True,
        }
    ]


def sanitize_filename(filename):
    filename = os.path.basename((filename or "").strip())
    if not filename or not SAFE_FILENAME_RE.match(filename):
        return ""
    return filename


def normalize_files(files, *, coding_question):
    if not isinstance(files, list):
        files = []
    if not files:
        files = build_starter_files(coding_question)

    normalized = []
    seen_names = set()
    for item in files:
        if not isinstance(item, dict):
            continue
        name = sanitize_filename(item.get("name"))
        if not name or name in seen_names:
            continue
        content = str(item.get("content", ""))
        if len(content.encode("utf-8")) > MAX_CODE_BYTES:
            content = content.encode("utf-8")[:MAX_CODE_BYTES].decode("utf-8", errors="ignore")
        language = file_language_for_name(name, coding_question.language)
        normalized.append(
            {
                "name": name,
                "content": content,
                "language": language,
                "is_main": bool(item.get("is_main")),
            }
        )
        seen_names.add(name)

    if not normalized:
        normalized = build_starter_files(coding_question)

    if not coding_question.allow_multiple_files:
        main_file = next((item for item in normalized if item["is_main"]), normalized[0])
        main_file["is_main"] = True
        normalized = [main_file]

    if not any(item["is_main"] for item in normalized):
        normalized[0]["is_main"] = True
    else:
        main_seen = False
        for item in normalized:
            if item["is_main"] and not main_seen:
                main_seen = True
            elif item["is_main"]:
                item["is_main"] = False

    return normalized


def get_main_file(files):
    return next((item for item in files if item.get("is_main")), files[0] if files else None)


def truncate_capture(value):
    encoded = (value or "").encode("utf-8", errors="ignore")
    if len(encoded) <= MAX_CAPTURE_BYTES:
        return value or ""
    return encoded[:MAX_CAPTURE_BYTES].decode("utf-8", errors="ignore")


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


def _write_files(workspace, files):
    for item in files:
        path = workspace / item["name"]
        path.write_text(item.get("content", ""), encoding="utf-8")


def _container_command(language, files):
    main_file = get_main_file(files)
    main_name = main_file["name"] if main_file else ""
    if language == "python":
        return ["python", main_name or "main.py"]
    if language == "javascript":
        return ["node", main_name or "main.js"]
    if language == "cpp":
        source = main_name or "main.cpp"
        return ["sh", "-lc", f"g++ /workspace/{source} -O2 -std=c++17 -o /tmp/main && /tmp/main"]
    if language == "java":
        source = main_name or "Main.java"
        return ["sh", "-lc", f"cp -R /workspace /tmp/work && cd /tmp/work && javac {source} && java Main"]
    return []


def execute_code(*, language, files, stdin, time_limit_seconds, memory_limit_mb):
    if language == CodingExamQuestion.LANGUAGE_HTML:
        return ExecutionResult(status=CodingSubmission.STATUS_SUCCESS, output="Preview rendered in browser.")

    backend = getattr(settings, "CODING_EXECUTION_BACKEND", "docker")
    if backend != "docker":
        return ExecutionResult(
            status=CodingSubmission.STATUS_SANDBOX_UNAVAILABLE,
            error="Code execution is configured for Docker sandboxing, but Docker execution is disabled.",
        )

    if shutil.which("docker") is None:
        return ExecutionResult(
            status=CodingSubmission.STATUS_SANDBOX_UNAVAILABLE,
            error="Docker sandbox is not available on this server.",
        )

    image = getattr(settings, "CODING_EXECUTION_DOCKER_IMAGES", {}).get(language) or DOCKER_IMAGES.get(language)
    command = _container_command(language, files)
    if not image or not command:
        return ExecutionResult(
            status=CodingSubmission.STATUS_SANDBOX_UNAVAILABLE,
            error="No sandbox image is configured for this language.",
        )

    with tempfile.TemporaryDirectory(prefix="emsarena-code-") as tmp:
        workspace = Path(tmp)
        _write_files(workspace, files)
        docker_command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            f"{max(int(memory_limit_mb or 128), 16)}m",
            "--cpus",
            "1",
            "--pids-limit",
            "64",
            "--read-only",
            "--tmpfs",
            "/tmp:rw,nosuid,size=128m",
            "-v",
            f"{workspace}:/workspace:ro",
            "-w",
            "/workspace",
            image,
            *command,
        ]
        start = time.perf_counter()
        try:
            completed = subprocess.run(  # nosec B603 - Docker is the sandbox boundary; no shell on the host.
                docker_command,
                input=stdin or "",
                text=True,
                capture_output=True,
                timeout=max(int(time_limit_seconds or 2), 1) + 2,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            return ExecutionResult(
                status=CodingSubmission.STATUS_TIMEOUT,
                output=truncate_capture(exc.stdout or ""),
                error=truncate_capture(exc.stderr or "Execution timed out."),
                execution_time_ms=elapsed_ms,
            )

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    output = truncate_capture(completed.stdout)
    error = truncate_capture(completed.stderr)
    if completed.returncode == 0:
        return ExecutionResult(
            status=CodingSubmission.STATUS_SUCCESS,
            output=output,
            error=error,
            execution_time_ms=elapsed_ms,
        )

    status = CodingSubmission.STATUS_RUNTIME_ERROR
    if language in {"cpp", "java"} and error:
        status = CodingSubmission.STATUS_COMPILE_ERROR
    return ExecutionResult(status=status, output=output, error=error, execution_time_ms=elapsed_ms)


def normalize_output(value):
    return (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def run_visible_code(*, coding_question, selected_language, files, stdin=""):
    if not coding_question.enable_code_execution:
        return {
            "status": CodingSubmission.STATUS_EXECUTION_DISABLED,
            "output": "",
            "error": "Code execution is disabled for this exam.",
            "test_results": [],
            "score": None,
            "execution_time_ms": None,
            "memory_usage_kb": None,
        }

    files = normalize_files(files, coding_question=coding_question)
    visible_cases = list(coding_question.test_cases.filter(visibility=CodingTestCase.VISIBILITY_VISIBLE))
    if not visible_cases:
        result = execute_code(
            language=selected_language,
            files=files,
            stdin=stdin,
            time_limit_seconds=coding_question.time_limit_seconds,
            memory_limit_mb=coding_question.memory_limit_mb,
        )
        return {
            "status": result.status,
            "output": result.output,
            "error": result.error,
            "test_results": [],
            "score": None,
            "execution_time_ms": result.execution_time_ms,
            "memory_usage_kb": result.memory_usage_kb,
        }

    return grade_files_against_tests(
        coding_question=coding_question, selected_language=selected_language, files=files, include_hidden=False
    )


def grade_files_against_tests(*, coding_question, selected_language, files, include_hidden):
    if not coding_question.enable_code_execution:
        return {
            "status": CodingSubmission.STATUS_EXECUTION_DISABLED,
            "output": "",
            "error": "Code execution is disabled for this exam.",
            "test_results": [],
            "score": None,
            "execution_time_ms": None,
            "memory_usage_kb": None,
        }

    files = normalize_files(files, coding_question=coding_question)
    test_cases = list(
        coding_question.test_cases.all()
        if include_hidden
        else coding_question.test_cases.filter(visibility=CodingTestCase.VISIBILITY_VISIBLE)
    )
    if not test_cases:
        return run_visible_code(coding_question=coding_question, selected_language=selected_language, files=files)

    results = []
    total_score = Decimal("0")
    last_result = ExecutionResult(status=CodingSubmission.STATUS_SUCCESS)
    for test_case in test_cases:
        execution = execute_code(
            language=selected_language,
            files=files,
            stdin=test_case.input_data,
            time_limit_seconds=coding_question.time_limit_seconds,
            memory_limit_mb=coding_question.memory_limit_mb,
        )
        last_result = execution
        passed = execution.status == CodingSubmission.STATUS_SUCCESS and normalize_output(
            execution.output
        ) == normalize_output(test_case.expected_output)
        if passed:
            total_score += Decimal(test_case.point_value)
        results.append(
            {
                "id": test_case.id,
                "visibility": test_case.visibility,
                "input": test_case.input_data if test_case.visibility == CodingTestCase.VISIBILITY_VISIBLE else "",
                "expected": (
                    test_case.expected_output if test_case.visibility == CodingTestCase.VISIBILITY_VISIBLE else ""
                ),
                "actual": execution.output if test_case.visibility == CodingTestCase.VISIBILITY_VISIBLE else "",
                "status": execution.status,
                "passed": passed,
                "points": test_case.point_value,
                "error": execution.error if test_case.visibility == CodingTestCase.VISIBILITY_VISIBLE else "",
                "execution_time_ms": execution.execution_time_ms,
            }
        )
        if execution.status in {CodingSubmission.STATUS_SANDBOX_UNAVAILABLE, CodingSubmission.STATUS_TIMEOUT}:
            break

    final_status = CodingSubmission.STATUS_SUCCESS if all(item["passed"] for item in results) else last_result.status
    if any(not item["passed"] for item in results) and final_status == CodingSubmission.STATUS_SUCCESS:
        final_status = CodingSubmission.STATUS_RUNTIME_ERROR

    return {
        "status": final_status,
        "output": last_result.output,
        "error": last_result.error,
        "test_results": results,
        "score": total_score,
        "execution_time_ms": last_result.execution_time_ms,
        "memory_usage_kb": last_result.memory_usage_kb,
    }
