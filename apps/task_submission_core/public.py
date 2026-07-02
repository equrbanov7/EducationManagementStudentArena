"""task_submission_core modulunun PUBLIC API fasadı (M3-B, 2026-07-02).

assignments/labs/projects üçün ortaq təhvil axını — bu üç modul yalnız bu
fasadla işləməlidir (AGENTS §5).
"""

from apps.task_submission_core.access import (  # noqa: F401
    can_user_access_course_roster,
)
from apps.task_submission_core.navigation import (  # noqa: F401
    build_student_task_back_url,
    build_teacher_review_back_url,
    student_return_to,
)
from apps.task_submission_core.review import (  # noqa: F401
    annotate_student_review_state,
    annotate_teacher_review_state,
    apply_submission_filters,
    build_pagination_query,
    resolve_identity_window,
    resolve_recheck_window,
)
from apps.task_submission_core.services import (  # noqa: F401
    apply_grade,
    assign_task_to_group,
    assign_task_to_students,
    bulk_grade_submissions,
    create_submission,
    get_pending_task_submissions,
    get_task_submissions,
    parse_score_value,
    update_submission,
)
from apps.task_submission_core.uploads import (  # noqa: F401
    prepare_submission_upload,
)

__all__ = [
    "annotate_student_review_state",
    "annotate_teacher_review_state",
    "apply_grade",
    "apply_submission_filters",
    "assign_task_to_group",
    "assign_task_to_students",
    "build_pagination_query",
    "build_student_task_back_url",
    "build_teacher_review_back_url",
    "bulk_grade_submissions",
    "can_user_access_course_roster",
    "create_submission",
    "get_pending_task_submissions",
    "get_task_submissions",
    "parse_score_value",
    "prepare_submission_upload",
    "resolve_identity_window",
    "resolve_recheck_window",
    "student_return_to",
    "update_submission",
]
