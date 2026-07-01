"""coding_runtime paketi — grading."""

from decimal import Decimal

from apps.exams.models import CodingSubmission, CodingTestCase

from ._shared import (
    ExecutionResult,
    normalize_output,
)
from .files import (
    normalize_files,
)


def _facade_execute_code():
    """`execute_code`-u paket fasadından götür — testlər onu
    patch("...coding_runtime.execute_code") ilə əvəz edir (bölgüdən sonra patch
    fasada dəyir, ona görə call-time həll edirik)."""
    from apps.exams.services import coding_runtime as _facade

    return _facade.execute_code


def run_visible_code(*, coding_question, selected_language, files, stdin=""):
    execute_code = _facade_execute_code()
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
    execute_code = _facade_execute_code()
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
