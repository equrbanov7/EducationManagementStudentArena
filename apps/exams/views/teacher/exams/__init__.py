"""teacher exams — geriyə-uyğun fasad paketi."""

from .actions import (  # noqa: F401
    delete_exam,
    duplicate_exam,
    permanent_delete_exam,
    restore_exam,
    toggle_exam_active,
    toggle_exam_archive,
    toggle_exam_results_visibility,
)
from .assignee_edit import exam_assignees_update  # noqa: F401
from .assignees import teacher_exam_assignees  # noqa: F401
from .attempt_grants import grant_extra_attempt, grant_extra_attempt_group  # noqa: F401
from .list_detail import (  # noqa: F401
    createAndEditExamView,
    teacher_exam_detail,
    teacher_exam_detail_questions_page,
    teacher_exam_list,
)
from .lookups import (  # noqa: F401
    assigned_student_count,
    bank_teacher_search,
    group_search,
    invigilator_search,
    subject_search,
    user_search,
)
from .lookups_journal import journal_teacher_subjects  # noqa: F401
from .unit_coverage import unit_journal_coverage  # noqa: F401

__all__ = [
    "assigned_student_count",
    "bank_teacher_search",
    "invigilator_search",
    "createAndEditExamView",
    "delete_exam",
    "exam_assignees_update",
    "duplicate_exam",
    "permanent_delete_exam",
    "restore_exam",
    "grant_extra_attempt",
    "grant_extra_attempt_group",
    "group_search",
    "journal_teacher_subjects",
    "subject_search",
    "teacher_exam_assignees",
    "teacher_exam_detail",
    "teacher_exam_detail_questions_page",
    "teacher_exam_list",
    "toggle_exam_active",
    "toggle_exam_archive",
    "toggle_exam_results_visibility",
    "unit_journal_coverage",
    "user_search",
]
