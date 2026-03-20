"""
Labs Views - Main Export File
Bütün view-ların re-export edilməsi
"""

# ═══════════════════════════════════════════════════════════════════════════════
# BLOCK CRUD
# ═══════════════════════════════════════════════════════════════════════════════
from .blocks import (
    create_block,
    delete_block,
    edit_block,
    manage_blocks,
    update_questions_per_student,
)

# ═══════════════════════════════════════════════════════════════════════════════
# LAB CRUD
# ═══════════════════════════════════════════════════════════════════════════════
from .crud import create_lab, delete_lab, edit_lab, publish_lab

# ═══════════════════════════════════════════════════════════════════════════════
# PREVIEW
# ═══════════════════════════════════════════════════════════════════════════════
from .preview import preview_randomization

# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION CRUD
# ═══════════════════════════════════════════════════════════════════════════════
from .questions import create_question, delete_question, edit_question, import_questions

# ═══════════════════════════════════════════════════════════════════════════════
# STUDENT VIEWS
# ═══════════════════════════════════════════════════════════════════════════════
from .student import api_get_groups, api_get_students, lab_detail, my_lab_answers

# ═══════════════════════════════════════════════════════════════════════════════
# SUBMISSIONS & GRADING
# ═══════════════════════════════════════════════════════════════════════════════
from .submissions import (
    auto_save_answer,
    delete_submissions,
    grade_submission_page,
    lab_submissions,
    submission_answers,
    submit_lab,
)

# ═══════════════════════════════════════════════════════════════════════════════
# __all__ - Export ediləcək bütün funksiyalar
# ═══════════════════════════════════════════════════════════════════════════════
__all__ = [
    # Lab CRUD
    "create_lab",
    "edit_lab",
    "delete_lab",
    "publish_lab",
    # Block CRUD
    "manage_blocks",
    "create_block",
    "edit_block",
    "delete_block",
    "update_questions_per_student",
    # Question CRUD
    "create_question",
    "edit_question",
    "delete_question",
    "import_questions",
    # Submissions & Grading
    "lab_submissions",
    "delete_submissions",
    "grade_submission_page",
    "auto_save_answer",
    "submit_lab",
    "submission_answers",
    # Preview
    "preview_randomization",
    # Student Views
    "lab_detail",
    "my_lab_answers",
    "api_get_groups",
    "api_get_students",
]
