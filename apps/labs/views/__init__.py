"""
labs/views/__init__.py — FASAD.

F2 rol-skeleti (2026-07-02, AGENTS §6): fayllar views/{student,teacher,shared}/
qovluqlarına köçürülüb; submissions.py rol üzrə bölünüb (student: autosave/submit,
teacher: siyahı/qiymətləndirmə). Mövcud import səthi dəyişmir.
"""

from .shared import api_get_groups, api_get_students
from .student import auto_save_answer, lab_detail, my_lab_answers, submit_lab
from .teacher import (
    create_block,
    create_lab,
    create_question,
    delete_block,
    delete_lab,
    delete_question,
    delete_submissions,
    edit_block,
    edit_lab,
    edit_question,
    grade_submission_page,
    import_questions,
    lab_submissions,
    manage_blocks,
    preview_randomization,
    publish_lab,
    submission_answers,
    update_questions_per_student,
)

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
    "auto_save_answer",
    "submit_lab",
    "submission_answers",
    "preview_randomization",
    "lab_detail",
    "my_lab_answers",
    "api_get_groups",
    "api_get_students",
]
