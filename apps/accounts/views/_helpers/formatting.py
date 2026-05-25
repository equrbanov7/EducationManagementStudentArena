"""
URL building, query-string and value-normalization helpers.

These are small, dependency-free utilities reused across account views.
"""

from decimal import InvalidOperation
from urllib.parse import urlencode

from core.helpers import ASSIGNED_TASK_FILTER_CHOICES

from ...services import parse_decimal_score
from .constants import (
    PENDING_ANSWER_FILTER_CHOICES,
    PENDING_REVIEW_STATUS_CHOICES,
    PENDING_REVIEW_TYPE_CHOICES,
    RESULT_FILTER_CHOICES,
)


def _append_query_params(url, **params):
    clean_params = {key: value for key, value in params.items() if value not in (None, "")}
    if not clean_params:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(clean_params)}"


def _query_string(**params):
    clean_params = {key: value for key, value in params.items() if value not in (None, "")}
    return urlencode(clean_params)


def _normalized_org_name(value):
    return " ".join((value or "").strip().lower().split())


def _parse_decimal_score(raw_value):
    score = parse_decimal_score((raw_value or "").strip().replace(",", "."), default=None)
    if score is None:
        raise InvalidOperation
    return score


def _result_status_badge(status, is_graded=False):
    """Normalize source-specific statuses into submitted/graded/pending."""
    if is_graded:
        return "graded"

    normalized_status = (status or "").lower()
    if normalized_status in {"graded"}:
        return "graded"
    if normalized_status in {"grading", "returned", "rejected", "expired", "draft", "in_progress"}:
        return "pending"
    return "submitted"


def _normalize_results_filter(value):
    normalized = (value or "all").lower()
    if normalized in RESULT_FILTER_CHOICES:
        return normalized
    return "all"


def _normalize_pending_answers_filter(value):
    normalized = (value or "all").lower()
    if normalized in PENDING_ANSWER_FILTER_CHOICES:
        return normalized
    return "all"


def _normalize_assigned_tasks_filter(value):
    normalized = (value or "all").lower()
    if normalized in ASSIGNED_TASK_FILTER_CHOICES:
        return normalized
    return "all"


def _normalize_pending_review_type(value):
    normalized = (value or "all").lower()
    if normalized in PENDING_REVIEW_TYPE_CHOICES:
        return normalized
    return "all"


def _normalize_pending_review_status(value):
    normalized = (value or "all").lower()
    if normalized in PENDING_REVIEW_STATUS_CHOICES:
        return normalized
    return "all"


def _csv_to_int_set(raw_value):
    values = set()
    for chunk in (raw_value or "").split(","):
        token = chunk.strip()
        if token.isdigit():
            values.add(int(token))
    return values


def _csv_to_lower_token_set(raw_value):
    return {chunk.strip().lower() for chunk in (raw_value or "").split(",") if chunk.strip()}


def _task_state_badge_data(state):
    normalized_state = (state or "open").lower()
    if normalized_state == "upcoming":
        return "Gözləyir", "upcoming"
    if normalized_state == "closed":
        return "Bağlı", "closed"
    return "Aktiv", "open"


def _standard_item_type_meta(raw_type):
    normalized = (raw_type or "").strip().lower()
    if normalized == "exam":
        return {"type": "exam", "label": "İmtahan", "icon": "exam"}
    if normalized == "assignment":
        return {"type": "assignment", "label": "Sərbəst iş", "icon": "assignment"}
    if normalized == "lab":
        return {"type": "lab", "label": "Lab işi", "icon": "lab"}
    if normalized == "project":
        return {"type": "project", "label": "Kurs işi", "icon": "project"}
    if normalized == "course":
        return {"type": "course", "label": "Kurs", "icon": "course"}
    return {"type": "unknown", "label": "Tapşırıq", "icon": "task"}
