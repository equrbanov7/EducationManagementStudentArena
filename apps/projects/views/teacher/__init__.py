"""Müəllim səthi (F1 rol-skeleti, 2026-07-02): CRUD + yoxlama axınları."""

from .crud import create_project, delete_project, edit_project
from .endpoints import delete_submissions, grade_submission, review_submissions

__all__ = [
    "create_project",
    "delete_project",
    "edit_project",
    "delete_submissions",
    "grade_submission",
    "review_submissions",
]
