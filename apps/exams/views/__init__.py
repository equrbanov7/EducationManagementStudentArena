# exams/views/__init__.py

# ═══════════════════════════════════════════════════════════════
# SHARED VIEWS (bütün user-lər üçün ortaq)
# ═══════════════════════════════════════════════════════════════
from .shared.access import exam_code_check
from .student.attempts import start_exam, take_exam
from .student.coding import coding_autosave, coding_run, coding_submission_download, coding_submit
from .student.lists import assigned_student_exam_list, student_exam_list

# ═══════════════════════════════════════════════════════════════
# STUDENT VIEWS
# ═══════════════════════════════════════════════════════════════
from .student.results import exam_result, student_exam_history
from .teacher.exams import (
    createAndEditExamView,
    delete_exam,
    teacher_exam_detail,
    teacher_exam_list,
    toggle_exam_active,
    toggle_exam_results_visibility,
)

# ═══════════════════════════════════════════════════════════════
# TEACHER VIEWS
# ═══════════════════════════════════════════════════════════════
from .teacher.groups import (
    create_student_group,
    teacher_create_group,
    teacher_delete_group,
    teacher_group_list,
    teacher_remove_student_from_group,
    teacher_update_group,
)
from .teacher.languages import exam_language_manager
from .teacher.question_bank import (
    ai_generate_question_bank,
    create_question_bank,
    process_question_bank,
    test_question_bank,
    test_question_bank_template_download,
)
from .teacher.question_library import exam_bank_picker, question_bank_detail, question_bank_list
from .teacher.questions import add_exam_question, delete_exam_question, edit_exam_question, teacher_questions_bank
from .teacher.results import (
    ai_grade_answer,
    delete_exam_attempts,
    export_exam_results_xlsx,
    teacher_check_attempt,
    teacher_exam_results,
    teacher_pending_attempts,
    teacher_view_attempt,
)
from .teacher.statistics import teacher_exam_statistics
from .teacher.supervision import (
    attempt_live_snapshot_api,
    exam_live_monitor,
    exam_live_monitor_poll_api,
    log_incident_api,
    supervision_detail,
    supervision_monitor,
    supervision_status_api,
    teacher_lock_api,
    teacher_resume_api,
    teacher_stop_api,
)

# ═══════════════════════════════════════════════════════════════
# __all__ - Export ediləcək bütün funksiyalar
# ═══════════════════════════════════════════════════════════════
__all__ = [
    # Shared
    "exam_code_check",
    # Teacher - Groups
    "teacher_group_list",
    "teacher_create_group",
    "teacher_update_group",
    "teacher_delete_group",
    "create_student_group",
    "teacher_remove_student_from_group",
    # Teacher - Exams
    "teacher_exam_list",
    "createAndEditExamView",
    "teacher_exam_detail",
    "toggle_exam_active",
    "toggle_exam_results_visibility",
    "delete_exam",
    # Teacher - Questions
    "add_exam_question",
    "edit_exam_question",
    "delete_exam_question",
    "teacher_questions_bank",
    # Teacher - Question Bank
    "create_question_bank",
    "process_question_bank",
    "test_question_bank",
    "test_question_bank_template_download",
    "ai_generate_question_bank",
    # Teacher - Results
    "teacher_exam_results",
    "delete_exam_attempts",
    "export_exam_results_xlsx",
    "teacher_view_attempt",
    "teacher_check_attempt",
    "teacher_pending_attempts",
    "ai_grade_answer",
    # Teacher - Statistics
    "teacher_exam_statistics",
    # Teacher - Language variants
    "exam_language_manager",
    # Teacher - Question bank library + picker
    "question_bank_list",
    "question_bank_detail",
    "exam_bank_picker",
    # Teacher - Supervision
    "supervision_monitor",
    "supervision_detail",
    "exam_live_monitor",
    "exam_live_monitor_poll_api",
    "attempt_live_snapshot_api",
    "teacher_lock_api",
    "teacher_resume_api",
    "teacher_stop_api",
    "log_incident_api",
    "supervision_status_api",
    # Student - Results
    "exam_result",
    "student_exam_history",
    # Student - Attempts
    "start_exam",
    "take_exam",
    "coding_autosave",
    "coding_run",
    "coding_submission_download",
    "coding_submit",
    # Student - Lists
    "assigned_student_exam_list",
    "student_exam_list",
]
