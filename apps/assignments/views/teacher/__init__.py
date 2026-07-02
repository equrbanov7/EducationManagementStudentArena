"""Müəllim səthi (F1 rol-skeleti, 2026-07-02): CRUD + yoxlama axınları."""

from .crud import create_assignment, delete_assignment, edit_assignment
from .endpoints import delete_submissions, grade_submission, review_submissions

__all__ = [
    "create_assignment",
    "delete_assignment",
    "edit_assignment",
    "delete_submissions",
    "grade_submission",
    "review_submissions",
]
