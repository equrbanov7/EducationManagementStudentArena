"""
Small shared formatting / normalization helpers for the dashboard collectors.
"""

from decimal import Decimal, InvalidOperation

from django.db.models import Q

from apps.exams.models import StudentGroup

from .._helpers import PENDING_REVIEW_STATUS_CHOICES, PENDING_REVIEW_TYPE_CHOICES
from .constants import SUBMISSION_DATE_ORDER_CHOICES


def _user_display_name(user):
    return user.get_full_name() or user.username


def _build_student_group_map_and_available(teacher):
    """Build student→group_name mapping and available groups list from StudentGroup model."""
    teacher_groups = StudentGroup.objects.filter(Q(teacher=teacher) | Q(teachers=teacher)).distinct()
    student_group_pairs = teacher_groups.values_list("students__id", "name")
    student_group_map = {}
    for student_id, group_name in student_group_pairs:
        if student_id and group_name:
            student_group_map[student_id] = group_name
    available_groups = sorted(
        {g.name for g in teacher_groups if g.name},
        key=str.lower,
    )
    return student_group_map, available_groups


def _standard_item_type_meta(raw_type):
    normalized = (raw_type or "").lower()
    mapping = {
        "courses": ("Kurs", "fas fa-graduation-cap"),
        "assignments": ("Sərbəst iş", "fas fa-file-signature"),
        "independent": ("Kurs işi", "fas fa-diagram-project"),
        "projects": ("Kurs işi", "fas fa-diagram-project"),
        "labs": ("Lab işi", "fas fa-flask"),
        "lab": ("Lab işi", "fas fa-flask"),
        "exams": ("İmtahan", "fas fa-file-alt"),
        "exam": ("İmtahan", "fas fa-file-alt"),
    }
    return mapping.get(normalized, ("Tapşırıq", "fas fa-file"))


def _resolve_teacher_review_action(*, is_graded=False, in_recheck_window=False):
    if in_recheck_window:
        return "Yenidən yoxla"
    if is_graded:
        return "Bax"
    return "Yoxla"


def _normalize_submission_date_order(value, *, default="newest"):
    normalized = (value or default).lower()
    if normalized in SUBMISSION_DATE_ORDER_CHOICES:
        return normalized
    return default


def _format_score_display(value):
    if value in (None, ""):
        return "-"

    try:
        formatted = format(Decimal(str(value)), "f")
    except (InvalidOperation, TypeError, ValueError):
        return str(value)

    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted or "0"


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
