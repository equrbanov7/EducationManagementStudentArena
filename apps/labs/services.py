"""
Compatibility exports for the split labs service modules.
"""

from .lab_access import get_lab_submissions, get_pending_lab_submissions
from .lab_assignment_service import create_lab_assignments_for_students, get_lab_assignment_for_student
from .lab_grading_service import calculate_lab_total_score, grade_lab_answer, grade_lab_submission, parse_score_value
from .lab_submission_service import auto_save_lab_answers, create_lab_submission, update_lab_submission

__all__ = [
    "auto_save_lab_answers",
    "calculate_lab_total_score",
    "create_lab_assignments_for_students",
    "create_lab_submission",
    "get_lab_assignment_for_student",
    "get_lab_submissions",
    "get_pending_lab_submissions",
    "grade_lab_answer",
    "grade_lab_submission",
    "parse_score_value",
    "update_lab_submission",
]
