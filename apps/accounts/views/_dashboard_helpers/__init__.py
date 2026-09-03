"""
Dashboard helper collectors.

Split out of a single ~1,390-line ``_dashboard_helpers.py`` module. The five
large ``_collect_*`` functions now live in one module each, with the small
shared formatting helpers in ``formatters``. This ``__init__`` re-exports every
public name so existing ``from ._dashboard_helpers import ...`` callers
(``dashboard`` views and ``profile/main``) keep working unchanged.

Modules:
* ``constants``        — submission date-order choices
* ``formatters``       — small shared format/normalize helpers
* ``assigned_tasks``   — ``_collect_assigned_tasks``
* ``results``          — ``_collect_my_results``
* ``academic_results`` — registrar/jurnal fənn nəticələri (``_collect_my_results``-un
  "academic" qolu; hesablama registrar fasadındadır, burada yalnız formatlama)
* ``pending_answers``  — ``_collect_pending_answer_items``
* ``pending_review``   — ``_collect_pending_review_items``
* ``evaluated_review`` — ``_collect_evaluated_review_items``
"""

from .academic_results import academic_filter_options, count_academic_items
from .assigned_tasks import _collect_assigned_tasks
from .constants import SUBMISSION_DATE_ORDER_CHOICES
from .evaluated_review import _collect_evaluated_review_items
from .formatters import (
    _build_student_group_map_and_available,
    _format_score_display,
    _normalize_pending_review_status,
    _normalize_pending_review_type,
    _normalize_submission_date_order,
    _resolve_teacher_review_action,
    _resolve_teacher_review_action_code,
    _standard_item_type_meta,
    _user_display_name,
)
from .pending_answers import _collect_pending_answer_items
from .pending_review import _collect_pending_review_items
from .results import _collect_my_results

__all__ = [
    "SUBMISSION_DATE_ORDER_CHOICES",
    "academic_filter_options",
    "count_academic_items",
    "_build_student_group_map_and_available",
    "_format_score_display",
    "_normalize_pending_review_status",
    "_normalize_pending_review_type",
    "_normalize_submission_date_order",
    "_resolve_teacher_review_action",
    "_resolve_teacher_review_action_code",
    "_standard_item_type_meta",
    "_user_display_name",
    "_collect_assigned_tasks",
    "_collect_my_results",
    "_collect_pending_answer_items",
    "_collect_pending_review_items",
    "_collect_evaluated_review_items",
]
