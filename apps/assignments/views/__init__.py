"""
assignments/views/__init__.py — FASAD.

F1 rol-skeleti (2026-07-02, AGENTS §6): fayllar views/{student,teacher,shared}/
rol qovluqlarına köçürülüb. Bu fasad bütün mövcud import səthini
(`from . import views` → views.create_assignment və s.) DƏYİŞMƏDƏN saxlayır.
"""

from .shared import remove_student_from_assignment, search_groups, search_students, students_by_groups
from .student import assignment_detail, my_submissions, submit_assignment
from .teacher import (
    create_assignment,
    delete_assignment,
    delete_submissions,
    edit_assignment,
    grade_submission,
    review_submissions,
)

__all__ = [
    "create_assignment",
    "edit_assignment",
    "delete_assignment",
    "assignment_detail",
    "submit_assignment",
    "my_submissions",
    "review_submissions",
    "delete_submissions",
    "grade_submission",
    "search_students",
    "search_groups",
    "students_by_groups",
    "remove_student_from_assignment",
]
