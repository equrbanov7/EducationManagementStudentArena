"""teacher exams — geriyə-uyğun fasad paketi."""

from .actions import (  # noqa: F401
    delete_exam,
    deleted_exams_list,
    duplicate_exam,
    permanent_delete_exam,
    restore_exam,
    toggle_exam_active,
    toggle_exam_archive,
    toggle_exam_results_visibility,
)
from .attempt_grants import grant_extra_attempt  # noqa: F401
from .list_detail import (  # noqa: F401
    createAndEditExamView,
    teacher_exam_detail,
    teacher_exam_detail_questions_page,
    teacher_exam_list,
)
from .lookups import (  # noqa: F401
    assigned_student_count,
    exam_available_question_count,
    group_search,
    invigilator_search,
    subject_search,
    user_search,
)

__all__ = [
    "assigned_student_count",
    "invigilator_search",
    "createAndEditExamView",
    "delete_exam",
    "deleted_exams_list",
    "duplicate_exam",
    "permanent_delete_exam",
    "restore_exam",
    "exam_available_question_count",
    "grant_extra_attempt",
    "group_search",
    "subject_search",
    "teacher_exam_detail",
    "teacher_exam_detail_questions_page",
    "teacher_exam_list",
    "toggle_exam_active",
    "toggle_exam_archive",
    "toggle_exam_results_visibility",
    "user_search",
]
