import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction

import requests

from apps.exams.models import CodingExamQuestion, CodingFile, CodingSubmission, CodingTestCase, ExamAnswer
from apps.exams.services.coding_polyfills import NODE_PROMPT_POLYFILL, javascript_main_has_top_level_input_loop

logger = logging.getLogger(__name__)

MAX_CODE_BYTES = 256_000
MAX_CAPTURE_BYTES = 64_000
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,180}$")
TRIPLE_QUOTE_RE = re.compile(r"(?<!\\)(\"\"\"|''')")


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


# Piston (https://github.com/engineer-man/piston) fallback used when Docker
# is unavailable on the host (typical for managed app platforms such as
# Heroku/Render/Railway). The mapping below uses Piston's `language` slugs.
# Versions are pinned to the highest stable Piston runtimes available on the
# public emkc.org instance as of 2026-05; "*" tells Piston to pick the latest
# installed runtime, which keeps us forward-compatible.
PISTON_LANGUAGES = {
    "python": ("python", "*"),
    "javascript": ("javascript", "*"),
    "cpp": ("c++", "*"),
    "java": ("java", "*"),
}

PISTON_FILE_NAMES = {
    "python": "main.py",
    "javascript": "main.js",
    "cpp": "main.cpp",
    "java": "Main.java",
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


def execution_language_for_filename(filename, fallback_language):
    language = file_language_for_name(filename, fallback_language)
    if language == "css":
        return CodingExamQuestion.LANGUAGE_HTML
    allowed_languages = {value for value, _ in CodingExamQuestion.LANGUAGE_CHOICES}
    return language if language in allowed_languages else fallback_language


def default_starter_code(language):
    if language == CodingExamQuestion.LANGUAGE_CPP:
        return "#include <iostream>\n" "using namespace std;\n\n" "int main() {\n" "    return 0;\n" "}\n"
    if language == CodingExamQuestion.LANGUAGE_JAVA:
        return "public class Main {\n" "    public static void main(String[] args) {\n" "    }\n" "}\n"
    return ""


def build_starter_files(coding_question):
    language = coding_question.language
    starter_code = coding_question.starter_code or ""
    if language == CodingExamQuestion.LANGUAGE_HTML:
        return [
            {
                "name": "index.html",
                "content": starter_code
                or (
                    "<!doctype html>\n"
                    '<html lang="en">\n'
                    "<head>\n"
                    '  <meta charset="UTF-8">\n'
                    '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
                    "  <title>Practical preview</title>\n"
                    '  <link rel="stylesheet" href="style.css">\n'
                    "</head>\n"
                    "<body>\n\n"
                    '  <script src="script.js"></script>\n'
                    "</body>\n"
                    "</html>\n"
                ),
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
            "content": starter_code or default_starter_code(language),
            "language": file_language_for_name(filename, language),
            "is_main": True,
        }
    ]


def sanitize_filename(filename):
    filename = os.path.basename((filename or "").strip())
    if not filename or not SAFE_FILENAME_RE.match(filename):
        return ""
    return filename


def _line_has_unclosed_triple_quote(line, current_quote=None):
    matches = list(TRIPLE_QUOTE_RE.finditer(line))
    if not matches:
        return current_quote

    quote = current_quote
    for match in matches:
        marker = match.group(1)
        if quote is None:
            quote = marker
        elif quote == marker:
            quote = None
    return quote


def _line_bracket_delta(line):
    code = line.split("#", 1)[0]
    return sum(1 for char in code if char in "([{") - sum(1 for char in code if char in ")]}")


def normalize_python_indentation(content):
    """Repair accidental tiny unindents that CodeMirror can leave hard to see."""
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    keep_trailing_newline = text.endswith("\n")
    lines = text.split("\n")
    if keep_trailing_newline:
        lines = lines[:-1]

    normalized_lines = []
    indent_stack = [0]
    bracket_depth = 0
    triple_quote = None
    explicit_continuation = False
    previous_opens_suite = False

    for raw_line in lines:
        line = raw_line
        leading_text = line[: len(line) - len(line.lstrip(" \t"))]
        expanded_leading = leading_text.expandtabs(4)
        leading = len(expanded_leading)
        stripped = line.lstrip(" \t")

        if stripped and triple_quote is None and bracket_depth <= 0 and not explicit_continuation:
            target_indent = leading
            current_indent = indent_stack[-1]
            if previous_opens_suite and leading > current_indent:
                if leading not in indent_stack:
                    indent_stack.append(leading)
            elif leading < current_indent and leading not in indent_stack:
                lower_indents = [value for value in indent_stack if value < leading]
                target_indent = max(lower_indents) if lower_indents else 0
            elif current_indent == 0 and 0 < leading < 4 and not previous_opens_suite:
                target_indent = 0

            if target_indent != leading or "\t" in leading_text:
                line = (" " * target_indent) + stripped
                leading = target_indent

            if leading < indent_stack[-1]:
                while len(indent_stack) > 1 and indent_stack[-1] > leading:
                    indent_stack.pop()

        normalized_lines.append(line)

        if not stripped:
            continue

        triple_quote = _line_has_unclosed_triple_quote(line, triple_quote)
        if triple_quote is None:
            bracket_depth = max(0, bracket_depth + _line_bracket_delta(line))
            explicit_continuation = line.rstrip().endswith("\\")
            previous_opens_suite = bracket_depth == 0 and line.rstrip().endswith(":")
        else:
            explicit_continuation = False
            previous_opens_suite = False

    return "\n".join(normalized_lines) + ("\n" if keep_trailing_newline else "")


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
        if language == "python":
            content = normalize_python_indentation(content)
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


def mark_file_as_main(files, filename):
    safe_name = sanitize_filename(filename)
    if not safe_name:
        return files
    if not any(item.get("name") == safe_name for item in files):
        return files
    return [{**item, "is_main": item.get("name") == safe_name} for item in files]


def truncate_capture(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    elif value is None:
        value = ""
    elif not isinstance(value, str):
        value = str(value)
    encoded = value.encode("utf-8", errors="ignore")
    if len(encoded) <= MAX_CAPTURE_BYTES:
        return value
    return encoded[:MAX_CAPTURE_BYTES].decode("utf-8", errors="ignore")


def _cpp_contains_main(content):
    return bool(re.search(r"\bmain\s*\(", content or ""))


def _wrap_cpp_snippet(content):
    prefix_lines = []
    body_lines = []
    for line in (content or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#include") or stripped.startswith("using "):
            prefix_lines.append(line)
        else:
            body_lines.append(line)

    header_lines = []
    if not any(re.match(r"\s*#include\s*<iostream>", line) for line in prefix_lines):
        header_lines.append("#include <iostream>")
    header_lines.extend(prefix_lines)
    if not any(re.match(r"\s*using\s+namespace\s+std\s*;", line) for line in prefix_lines):
        header_lines.append("using namespace std;")

    body = "\n".join(body_lines).strip("\n")
    indented_body = "\n".join(("    " + line if line.strip() else "") for line in body.splitlines())
    wrapped_lines = [*header_lines, "", "int main() {"]
    if indented_body:
        wrapped_lines.append(indented_body)
    wrapped_lines.extend(["    return 0;", "}"])
    return "\n".join(wrapped_lines) + "\n"


def prepare_files_for_execution(language, files):
    prepared_files = [dict(item) for item in files]

    if language == CodingExamQuestion.LANGUAGE_CPP:
        main_file = get_main_file(prepared_files)
        if main_file and not _cpp_contains_main(main_file.get("content", "")):
            main_file["content"] = _wrap_cpp_snippet(main_file.get("content", ""))
        return prepared_files

    if language == CodingExamQuestion.LANGUAGE_JAVASCRIPT:
        main_file = get_main_file(prepared_files)
        if main_file and not javascript_main_has_top_level_input_loop(main_file.get("content", "")):
            main_file["content"] = NODE_PROMPT_POLYFILL + (main_file.get("content", "") or "")
        return prepared_files

    return prepared_files


def _is_docker_pull_noise(line):
    stripped = line.strip()
    lower = stripped.lower()
    if not stripped:
        return True
    noise_fragments = (
        "pulling from",
        "pulling fs layer",
        "waiting",
        "download complete",
        "pull complete",
        "verifying checksum",
        "already exists",
        "downloaded newer image",
        "image is up to date",
    )
    if stripped.startswith("Unable to find image ") and stripped.endswith(" locally"):
        return True
    if stripped.startswith("Digest: sha256:"):
        return True
    return any(fragment in lower for fragment in noise_fragments)


def clean_docker_stderr(value):
    text = truncate_capture(value)
    lines = [line for line in text.splitlines() if not _is_docker_pull_noise(line)]
    return truncate_capture("\n".join(lines))


def _ensure_docker_image(image):
    try:
        inspect = subprocess.run(  # nosec B603 - image name is passed as one Docker argument.
            ["docker", "image", "inspect", image],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Unable to inspect Docker sandbox image: {exc}"

    if inspect.returncode == 0:
        return ""

    pull_timeout = int(getattr(settings, "CODING_EXECUTION_IMAGE_PULL_TIMEOUT_SECONDS", 180) or 180)
    try:
        pull = subprocess.run(  # nosec B603 - image name is passed as one Docker argument.
            ["docker", "pull", image],
            text=True,
            capture_output=True,
            timeout=max(pull_timeout, 30),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return "Timed out while preparing the Docker sandbox image."
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Unable to prepare Docker sandbox image: {exc}"

    if pull.returncode != 0:
        details = clean_docker_stderr(pull.stderr) or truncate_capture(pull.stdout)
        return details or "Unable to prepare Docker sandbox image."
    return ""


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
        source = shlex.quote(main_name or "main.cpp")
        return ["sh", "-lc", f"g++ /workspace/{source} -O2 -std=c++17 -o /tmp/main && /tmp/main"]
    if language == "java":
        source = main_name or "Main.java"
        class_name = Path(source).stem or "Main"
        return [
            "sh",
            "-lc",
            f"cp -R /workspace /tmp/work && cd /tmp/work && javac {shlex.quote(source)} && java {shlex.quote(class_name)}",
        ]
    return []


def _docker_available():
    """Docker is usable only when the CLI is installed AND the daemon answers.

    On managed app platforms (Render/Railway/Heroku) `docker` may be on PATH
    but the daemon socket isn't reachable — in that case we still need to
    fall through to the Piston fallback instead of returning sandbox_unavailable.
    """

    if shutil.which("docker") is None:
        return False
    try:
        probe = subprocess.run(  # nosec B603 - argv list, no shell, fixed cmd.
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def _resolve_execution_backend(language):
    """Decide which executor to use for `language`.

    - `disabled` / `none`: do not execute code.
    - `docker` (default): use Docker; if unavailable, return `none`.
    - `piston`: always use Piston regardless of Docker presence.
    - `auto` (recommended in production): prefer Docker, fall back to Piston
      when Docker is missing OR when the daemon isn't reachable.
    """

    raw = (getattr(settings, "CODING_EXECUTION_BACKEND", "docker") or "docker").lower()
    if raw in {"disabled", "none"}:
        return "none"
    if raw == "piston":
        return "piston"
    if raw == "auto":
        return "docker" if _docker_available() else "piston"
    # raw == "docker" (or any unknown value): legacy strict behavior.
    return "docker" if _docker_available() else "none"


def execute_code(*, language, files, stdin, time_limit_seconds, memory_limit_mb):
    if language == CodingExamQuestion.LANGUAGE_HTML:
        return ExecutionResult(status=CodingSubmission.STATUS_SUCCESS, output="Preview rendered in browser.")

    backend = _resolve_execution_backend(language)

    if backend == "piston":
        return _execute_via_piston(
            language=language,
            files=files,
            stdin=stdin,
            time_limit_seconds=time_limit_seconds,
            memory_limit_mb=memory_limit_mb,
        )

    if backend == "none":
        return ExecutionResult(
            status=CodingSubmission.STATUS_SANDBOX_UNAVAILABLE,
            error=(
                "Docker sandbox is not available on this server. "
                "Set CODING_EXECUTION_BACKEND=auto (or piston) to enable the "
                "hosted fallback executor."
            ),
        )

    image = getattr(settings, "CODING_EXECUTION_DOCKER_IMAGES", {}).get(language) or DOCKER_IMAGES.get(language)
    execution_files = prepare_files_for_execution(language, files)
    command = _container_command(language, execution_files)
    if not image or not command:
        return ExecutionResult(
            status=CodingSubmission.STATUS_SANDBOX_UNAVAILABLE,
            error="No sandbox image is configured for this language.",
        )

    image_error = _ensure_docker_image(image)
    if image_error:
        return ExecutionResult(
            status=CodingSubmission.STATUS_SANDBOX_UNAVAILABLE,
            error=image_error,
        )

    with tempfile.TemporaryDirectory(prefix="emsarena-code-") as tmp:
        workspace = Path(tmp)
        _write_files(workspace, execution_files)
        docker_command = [
            "docker",
            "run",
            "-i",
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
            "/tmp:rw,exec,nosuid,size=128m",
            "-v",
            f"{workspace}:/workspace:ro",
            "-w",
            "/workspace",
            image,
            *command,
        ]
        start = time.perf_counter()
        execution_timeout = max(int(time_limit_seconds or 2), 1) + (8 if language in {"cpp", "java"} else 2)
        try:
            completed = subprocess.run(  # nosec B603 - Docker is the sandbox boundary; no shell on the host.
                docker_command,
                input=stdin or "",
                text=True,
                capture_output=True,
                timeout=execution_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            timeout_error = clean_docker_stderr(exc.stderr)
            if timeout_error:
                timeout_error = f"{timeout_error}\nExecution timed out."
            else:
                timeout_error = "Execution timed out."
            return ExecutionResult(
                status=CodingSubmission.STATUS_TIMEOUT,
                output=truncate_capture(exc.stdout or ""),
                error=timeout_error,
                execution_time_ms=elapsed_ms,
            )

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    output = truncate_capture(completed.stdout)
    error = clean_docker_stderr(completed.stderr)
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


# ---------------------------------------------------------------------------
# Piston (hosted) execution backend
# ---------------------------------------------------------------------------
#
# Piston is a stateless code-execution HTTP API maintained by engineer-man.
# We use it as a fallback so practical exams keep working on production
# hosts that cannot run Docker (Render, Railway, Heroku, etc.).
#
# Security notes:
# - Submitted code is forwarded to the Piston server; it never executes
#   inside the Django process. This matches our Docker invariant.
# - Stdout/stderr are returned as strings; we truncate them to the same
#   MAX_CAPTURE_BYTES we use elsewhere so a malicious program cannot blow
#   up memory by emitting huge output.
# - Stdin is normalized before being forwarded; only what the student
#   supplied is sent.
# - We never send authentication tokens, session cookies, or organization
#   data to Piston — only the code itself.


def _piston_endpoint():
    base = getattr(settings, "CODING_PISTON_URL", "") or "https://emkc.org/api/v2/piston"
    return base.rstrip("/") + "/execute"


def _piston_files_payload(language, files):
    """Build Piston's `files` array from our internal files list.

    Piston requires the *main* file to be first; supplementary files are
    written next to it in the executor's temp directory. We honour the
    student's `is_main` flag the same way Docker does.
    """

    prepared = prepare_files_for_execution(language, files)
    main = get_main_file(prepared)
    if main is None:
        return []

    expected_main_name = PISTON_FILE_NAMES.get(language, main["name"])
    ordered = [main] + [item for item in prepared if item is not main]

    payload = []
    for index, item in enumerate(ordered):
        name = item.get("name") or expected_main_name
        # Java needs the entrypoint to be `Main.java`; rename only if we know
        # the public class name matches.
        if index == 0 and language == "java" and Path(name).stem != "Main":
            name = expected_main_name
        payload.append({"name": name, "content": item.get("content", "") or ""})
    return payload


def _execute_via_piston(*, language, files, stdin, time_limit_seconds, memory_limit_mb):
    piston_lang = PISTON_LANGUAGES.get(language)
    if not piston_lang:
        return ExecutionResult(
            status=CodingSubmission.STATUS_SANDBOX_UNAVAILABLE,
            error=f"Hosted executor does not support language: {language}.",
        )

    body = {
        "language": piston_lang[0],
        "version": piston_lang[1],
        "files": _piston_files_payload(language, files),
        "stdin": stdin or "",
        # Piston enforces server-side caps but accepts our preferred hints.
        "run_timeout": max(int(time_limit_seconds or 2), 1) * 1000 + 5000,
        "compile_timeout": 10000,
        "run_memory_limit": max(int(memory_limit_mb or 128), 64) * 1024 * 1024,
    }

    headers = {"Content-Type": "application/json"}
    auth_token = getattr(settings, "CODING_PISTON_AUTH_TOKEN", "") or ""
    if auth_token:
        headers["Authorization"] = auth_token

    # Retry policy for transient failures from the hosted runner:
    #   - 429 (rate-limited by emkc.org public API)
    #   - 502 / 503 / 504 (Piston worker restarting / overloaded)
    #   - Connection errors (transient TCP/DNS hiccups)
    # We back off briefly and retry; persistent failures still surface as
    # sandbox_unavailable to the student instead of hanging.
    request_timeout = max(int(time_limit_seconds or 2), 1) + 15
    max_attempts = 3
    backoff_seconds = 0.5

    response = None
    last_exception = None
    start = time.perf_counter()

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(
                _piston_endpoint(),
                json=body,
                headers=headers,
                timeout=request_timeout,
            )
        except requests.Timeout:
            return ExecutionResult(
                status=CodingSubmission.STATUS_TIMEOUT,
                error="Execution timed out while contacting the hosted runner.",
                execution_time_ms=int((time.perf_counter() - start) * 1000),
            )
        except requests.RequestException as exc:
            last_exception = exc
            logger.warning("Piston request failed (attempt %s/%s): %s", attempt, max_attempts, exc)
            if attempt < max_attempts:
                time.sleep(backoff_seconds * attempt)
                continue
            return ExecutionResult(
                status=CodingSubmission.STATUS_SANDBOX_UNAVAILABLE,
                error="Hosted code runner is currently unreachable. Please try again in a moment.",
            )

        # Retry on transient HTTP errors.
        if response.status_code in (429, 502, 503, 504) and attempt < max_attempts:
            # Respect Retry-After when the server provides it; otherwise use
            # exponential-ish backoff (0.5s, 1s, 1.5s).
            retry_after = response.headers.get("Retry-After")
            try:
                pause = float(retry_after) if retry_after else backoff_seconds * attempt
            except (TypeError, ValueError):
                pause = backoff_seconds * attempt
            time.sleep(min(pause, 3.0))
            continue

        break

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    if response is None:
        return ExecutionResult(
            status=CodingSubmission.STATUS_SANDBOX_UNAVAILABLE,
            error=f"Hosted code runner is unreachable: {last_exception or 'unknown error'}",
            execution_time_ms=elapsed_ms,
        )

    if response.status_code != 200:
        body_text = truncate_capture(response.text)
        # Translate the server's status code into something the UI can show
        # the student. 429 keeps its dedicated message so they understand
        # the issue is load, not their code.
        if response.status_code == 429:
            friendly = "The code runner is busy right now. Wait a few seconds and " "press Run again."
        else:
            friendly = f"Hosted runner error ({response.status_code}): {body_text}"
        return ExecutionResult(
            status=CodingSubmission.STATUS_SANDBOX_UNAVAILABLE,
            error=friendly,
            execution_time_ms=elapsed_ms,
        )

    try:
        data = response.json()
    except ValueError:
        return ExecutionResult(
            status=CodingSubmission.STATUS_SANDBOX_UNAVAILABLE,
            error="Hosted runner returned an invalid response.",
            execution_time_ms=elapsed_ms,
        )

    run = data.get("run") or {}
    compile_stage = data.get("compile") or {}

    compile_stdout = truncate_capture(compile_stage.get("stdout") or "")
    compile_stderr = truncate_capture(compile_stage.get("stderr") or "")
    stdout = truncate_capture(run.get("stdout") or "")
    stderr = truncate_capture(run.get("stderr") or "")

    # Compile failures: the run stage usually doesn't fire, but the compile
    # stderr explains what went wrong (think gcc/javac).
    if compile_stage.get("code") not in (None, 0):
        return ExecutionResult(
            status=CodingSubmission.STATUS_COMPILE_ERROR,
            output=compile_stdout,
            error=compile_stderr or "Compilation failed.",
            execution_time_ms=elapsed_ms,
        )

    run_code = run.get("code")
    signal = run.get("signal")
    if signal in {"SIGKILL", "SIGTERM"} and "time" in (stderr or "").lower():
        return ExecutionResult(
            status=CodingSubmission.STATUS_TIMEOUT,
            output=stdout,
            error=stderr or "Execution timed out.",
            execution_time_ms=elapsed_ms,
        )

    if run_code in (None, 0):
        return ExecutionResult(
            status=CodingSubmission.STATUS_SUCCESS,
            output=stdout,
            error=stderr,
            execution_time_ms=elapsed_ms,
        )

    return ExecutionResult(
        status=CodingSubmission.STATUS_RUNTIME_ERROR,
        output=stdout,
        error=stderr or f"Process exited with code {run_code}.",
        execution_time_ms=elapsed_ms,
    )


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
    if str(stdin or ""):
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
