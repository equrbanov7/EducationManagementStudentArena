"""Coding cəhdi — tələbəyə qaytarılan submission JSON-u (``coding.py``-dan ayrılıb, 600 sətir tavanı)."""


def _submission_payload(submission):
    if not submission:
        return None
    return {
        "id": submission.id,
        "status": submission.execution_status,
        "output": submission.output,
        "error": submission.error_message,
        # 2026-10-05 auditi (2-ci dalğa): nəticəsi gizli imtahanda run/autosave/səhifədə də bal yoxdur.
        "score": (
            None
            if submission.score is None or submission.exam.results_hidden_from_students
            else float(submission.score)
        ),
        "test_results": submission.test_results,
        "execution_time_ms": submission.execution_time_ms,
        "memory_usage_kb": submission.memory_usage_kb,
        "is_final": submission.is_final,
    }
