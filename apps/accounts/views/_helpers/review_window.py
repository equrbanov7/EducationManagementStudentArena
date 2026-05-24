"""
Review-window helpers.

After a submission is reviewed, teachers get a short edit window before the
result becomes visible to the student. These helpers compute that window.
"""

from django.utils import timezone

from .constants import REVIEW_EDIT_WINDOW


def _normalize_review_result_item_type(raw_type):
    normalized = (raw_type or "").strip().lower()
    if normalized in {"assignment", "assignments"}:
        return "assignment"
    if normalized in {"project", "projects"}:
        return "project"
    if normalized in {"lab", "labs"}:
        return "lab"
    return ""


def _pending_review_type_label(raw_type, *, exam_type=""):
    normalized = (raw_type or "").strip().lower()
    if normalized == "exam":
        if (exam_type or "").strip().lower() == "coding":
            return "Praktiki imtahan"
        return "Yazılı imtahan"
    if normalized == "assignment":
        return "Sərbəst iş"
    if normalized == "project":
        return "Kurs işi"
    if normalized == "lab":
        return "Lab işi"
    return "Tapşırıq"


def _is_review_window_closed(reviewed_at, *, now=None):
    if not reviewed_at:
        return False
    current_time = now or timezone.now()
    return current_time >= reviewed_at + REVIEW_EDIT_WINDOW


def _is_review_window_open(reviewed_at, *, now=None):
    if not reviewed_at:
        return False
    return not _is_review_window_closed(reviewed_at, now=now)


def _review_window_seconds_left(reviewed_at, *, now=None):
    if not reviewed_at:
        return 0
    current_time = now or timezone.now()
    remaining = int((reviewed_at + REVIEW_EDIT_WINDOW - current_time).total_seconds())
    return max(0, remaining)


def _is_result_visible_to_student(reviewed_at):
    if not reviewed_at:
        return False
    return _is_review_window_closed(reviewed_at)
