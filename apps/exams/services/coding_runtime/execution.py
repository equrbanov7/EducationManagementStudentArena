"""coding_runtime paketi — execution."""

import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from django.conf import settings

import requests

from apps.exams.models import CodingExamQuestion, CodingSubmission

from ._shared import (
    ExecutionResult,
    logger,
    truncate_capture,
)
from .constants import (
    DOCKER_IMAGES,
    PISTON_FILE_NAMES,
    PISTON_LANGUAGES,
)
from .files import (
    get_main_file,
    prepare_files_for_execution,
)


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
    # `_ensure_docker_image` testlərdə paket fasadı üzərindən patch olunur
    # (patch("...coding_runtime._ensure_docker_image")); bölgüdən sonra patch fasada
    # dəyir, ona görə adı call-time fasaddan həll edirik ki, mock təsirli olsun.
    from apps.exams.services import coding_runtime as _facade

    _ensure_docker_image = _facade._ensure_docker_image

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
