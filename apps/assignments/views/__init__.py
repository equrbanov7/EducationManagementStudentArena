"""
assignments/views/__init__.py
──────────────────────────────
Re-exports all views for backward compatibility with URLs.

This allows the existing urls.py to continue working with:
    from . import views
    views.create_assignment
"""

# ═══════════════════════════════════════════════════════════════
# API Views
# ═══════════════════════════════════════════════════════════════
from .api import remove_student_from_assignment, search_groups, search_students, students_by_groups

# ═══════════════════════════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════════════════════════
from .crud import create_assignment, delete_assignment, edit_assignment

# ═══════════════════════════════════════════════════════════════
# Student Views
# ═══════════════════════════════════════════════════════════════
from .student import assignment_detail, my_submissions, submit_assignment

# ═══════════════════════════════════════════════════════════════
# Teacher Views
# ═══════════════════════════════════════════════════════════════
from .teacher import delete_submissions, grade_submission, review_submissions

# ═══════════════════════════════════════════════════════════════
# __all__ - Explicit exports
# ═══════════════════════════════════════════════════════════════
__all__ = [
    # CRUD
    "create_assignment",
    "edit_assignment",
    "delete_assignment",
    # Student
    "assignment_detail",
    "submit_assignment",
    "my_submissions",
    # Teacher
    "review_submissions",
    "delete_submissions",
    "grade_submission",
    # API
    "search_students",
    "search_groups",
    "students_by_groups",
    "remove_student_from_assignment",
]
