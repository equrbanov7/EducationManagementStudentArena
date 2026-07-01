"""teacher exams — geriyə-uyğun fasad paketi."""

from .actions import (  # noqa: F401
    delete_exam,
    duplicate_exam,
    toggle_exam_active,
    toggle_exam_archive,
    toggle_exam_results_visibility,
)
from .list_detail import (  # noqa: F401
    createAndEditExamView,
    teacher_exam_detail,
    teacher_exam_detail_questions_page,
    teacher_exam_list,
)

__all__ = [
    "createAndEditExamView",
    "delete_exam",
    "duplicate_exam",
    "teacher_exam_detail",
    "teacher_exam_detail_questions_page",
    "teacher_exam_list",
    "toggle_exam_active",
    "toggle_exam_archive",
    "toggle_exam_results_visibility",
]
