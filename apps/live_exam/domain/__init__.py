"""
Live exam domain helpers.
"""

from .session import (
    detect_multi,
    get_active_question,
    get_current_exam_question,
    get_exam_question_ids,
    get_option_label,
    get_option_text,
    get_question_by_index,
    get_question_text,
    get_selected_question_ids,
    get_total_questions,
    question_points,
    question_time_limit,
    safe_int,
)

__all__ = [
    "detect_multi",
    "get_active_question",
    "get_current_exam_question",
    "get_exam_question_ids",
    "get_option_label",
    "get_option_text",
    "get_question_by_index",
    "get_question_text",
    "get_selected_question_ids",
    "get_total_questions",
    "question_points",
    "question_time_limit",
    "safe_int",
]
