"""coding_runtime paketi — _shared."""

import logging
import os
from dataclasses import dataclass

from apps.exams.models import CodingExamQuestion

from .constants import (
    MAX_CAPTURE_BYTES,
    SAFE_FILENAME_RE,
)

logger = logging.getLogger(__name__)


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


def sanitize_filename(filename):
    filename = os.path.basename((filename or "").strip())
    if not filename or not SAFE_FILENAME_RE.match(filename):
        return ""
    return filename


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


def normalize_output(value):
    return (value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
