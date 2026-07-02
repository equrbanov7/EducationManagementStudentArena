"""Müəllim səthi (F2 rol-skeleti, 2026-07-02)."""

from .blocks import create_block, delete_block, edit_block, manage_blocks, update_questions_per_student
from .crud import create_lab, delete_lab, edit_lab, publish_lab
from .preview import preview_randomization
from .questions import create_question, delete_question, edit_question, import_questions
from .submissions import delete_submissions, grade_submission_page, lab_submissions, submission_answers

__all__ = [
    "create_lab",
    "edit_lab",
    "delete_lab",
    "publish_lab",
    "manage_blocks",
    "create_block",
    "edit_block",
    "delete_block",
    "update_questions_per_student",
    "create_question",
    "edit_question",
    "delete_question",
    "import_questions",
    "lab_submissions",
    "delete_submissions",
    "grade_submission_page",
    "submission_answers",
    "preview_randomization",
]
