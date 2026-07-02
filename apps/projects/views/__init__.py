"""
projects/views/__init__.py — FASAD.

F1 rol-skeleti (2026-07-02, AGENTS §6): fayllar views/{student,teacher,shared}/
rol qovluqlarına köçürülüb. Mövcud import səthi dəyişmir.
"""

from .shared import api_get_groups, api_get_students
from .student import my_submissions, project_detail, submit_project
from .teacher import (
    create_project,
    delete_project,
    delete_submissions,
    edit_project,
    grade_submission,
    review_submissions,
)

__all__ = [
    "create_project",
    "edit_project",
    "delete_project",
    "project_detail",
    "submit_project",
    "my_submissions",
    "review_submissions",
    "delete_submissions",
    "grade_submission",
    "api_get_groups",
    "api_get_students",
]
