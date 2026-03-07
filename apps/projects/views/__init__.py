"""
projects/views/__init__.py
───────────────────────────
Re-exports all views for backward compatibility with URLs.

This allows the existing urls.py to continue working with:
    from . import views
    views.create_project
"""

# ═══════════════════════════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════════════════════════
from .crud import create_project, delete_project, edit_project

# ═══════════════════════════════════════════════════════════════
# Student Views
# ═══════════════════════════════════════════════════════════════
from .student import my_submissions, project_detail, submit_project

# ═══════════════════════════════════════════════════════════════
# Teacher Views
# ═══════════════════════════════════════════════════════════════
from .teacher import delete_submissions, grade_submission, review_submissions

# ═══════════════════════════════════════════════════════════════
# API Views
# ═══════════════════════════════════════════════════════════════
from .api import api_get_groups, api_get_students

# ═══════════════════════════════════════════════════════════════
# __all__ - Explicit exports
# ═══════════════════════════════════════════════════════════════
__all__ = [
    # CRUD
    "create_project",
    "edit_project",
    "delete_project",
    # Student
    "project_detail",
    "submit_project",
    "my_submissions",
    # Teacher
    "review_submissions",
    "delete_submissions",
    "grade_submission",
    # API
    "api_get_groups",
    "api_get_students",
]
