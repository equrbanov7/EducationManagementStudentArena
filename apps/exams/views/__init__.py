# exams/views/__init__.py

# ═══════════════════════════════════════════════════════════════
# SHARED VIEWS (bütün user-lər üçün ortaq)
# ═══════════════════════════════════════════════════════════════
from .exam_center import (
    exam_center_attempt_violations,
    exam_center_pin_lookup,
    exam_center_pin_search,
    exam_center_reports,
    exam_center_room_assign_invigilators,
    exam_center_room_end_all,
    exam_center_room_list,
    exam_center_room_monitor,
    exam_center_room_open_all,
    exam_center_room_snapshot,
    exam_center_room_start_all,
    exam_center_session_cancel,
    exam_center_session_create,
    exam_center_session_detail,
    exam_center_session_end,
    exam_center_session_history,
    exam_center_session_list,
    exam_center_session_monitor,
    exam_center_session_open_entry,
    exam_center_session_snapshot,
    exam_center_session_start,
    exam_center_stats_ai,
    exam_center_stats_charts,
    exam_center_stats_data,
    exam_center_stats_export,
    exam_center_stats_filters,
    exam_center_student_pins,
    exam_center_ticket_readmit,
    exam_center_ticket_reentry,
    exam_center_ticket_remove,
    exam_center_ticket_resume,
    exam_center_ticket_seat,
    exam_center_ticket_snapshot,
    stats_department_search,
    stats_faculty_search,
    stats_teacher_search,
)
from .shared.access import exam_code_check
from .student.attempts import start_exam, take_exam
from .student.coding import coding_autosave, coding_run, coding_submission_download, coding_submit
from .student.final_center import (
    final_exam_begin,
    final_exam_cancel,
    final_exam_entry,
    final_exam_waiting,
    final_ticket_state,
)
from .student.lists import assigned_student_exam_list, student_exam_list
from .student.question_timer import question_seen

# ═══════════════════════════════════════════════════════════════
# STUDENT VIEWS
# ═══════════════════════════════════════════════════════════════
from .student.results import exam_result, student_exam_history
from .teacher.exams import (
    assigned_student_count,
    createAndEditExamView,
    delete_exam,
    deleted_exams_list,
    duplicate_exam,
    exam_available_question_count,
    grant_extra_attempt,
    grant_extra_attempt_group,
    group_search,
    invigilator_search,
    permanent_delete_exam,
    restore_exam,
    subject_search,
    teacher_exam_detail,
    teacher_exam_detail_questions_page,
    teacher_exam_list,
    toggle_exam_active,
    toggle_exam_archive,
    toggle_exam_results_visibility,
    user_search,
)
from .teacher.extract_jobs import (
    export_job_download,
    export_job_waiting,
    start_text_extraction,
    text_extraction_status,
)

# ═══════════════════════════════════════════════════════════════
# TEACHER VIEWS
# ═══════════════════════════════════════════════════════════════
from .teacher.groups import (
    create_student_group,
    teacher_add_student_to_group,
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
    exam_questions_word_export,
    process_question_bank,
    test_question_bank,
    test_question_bank_template_download,
)
from .teacher.question_library import (
    ai_generate_bank_questions,
    bank_question_add,
    bank_question_edit,
    exam_bank_picker,
    question_bank_bulk_add,
    question_bank_delete,
    question_bank_detail,
    question_bank_list,
    question_bank_template_download,
    question_bank_update,
    question_bank_word_export,
)
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
from .teacher.submission_inbox import (
    ai_generate_submission_questions,
    question_submission_create,
    question_submission_decide,
    question_submission_delete,
    question_submission_detail,
    question_submission_inbox,
    question_submission_review,
)
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
    "start_text_extraction",
    "export_job_waiting",
    "export_job_download",
    "text_extraction_status",
    # Shared
    "exam_code_check",
    # Teacher - Groups
    "teacher_group_list",
    "teacher_create_group",
    "teacher_update_group",
    "teacher_delete_group",
    "create_student_group",
    "teacher_remove_student_from_group",
    "teacher_add_student_to_group",
    # Teacher - Exams
    "teacher_exam_list",
    "createAndEditExamView",
    "teacher_exam_detail",
    "teacher_exam_detail_questions_page",
    "toggle_exam_active",
    "toggle_exam_archive",
    "toggle_exam_results_visibility",
    "delete_exam",
    "deleted_exams_list",
    "restore_exam",
    "permanent_delete_exam",
    "duplicate_exam",
    "assigned_student_count",
    "exam_available_question_count",
    "grant_extra_attempt",
    "grant_extra_attempt_group",
    "group_search",
    "invigilator_search",
    "subject_search",
    "user_search",
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
    "ai_generate_submission_questions",
    "question_submission_create",
    "question_submission_decide",
    "question_submission_delete",
    "question_submission_detail",
    "question_submission_inbox",
    "question_submission_review",
    "question_bank_detail",
    "question_bank_update",
    "question_bank_delete",
    "question_bank_bulk_add",
    "question_bank_template_download",
    "question_bank_word_export",
    "exam_questions_word_export",
    "ai_generate_bank_questions",
    "bank_question_add",
    "bank_question_edit",
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
    "question_seen",
    "take_exam",
    "coding_autosave",
    "coding_run",
    "coding_submission_download",
    "coding_submit",
    # Student - Lists
    "assigned_student_exam_list",
    "student_exam_list",
    # Student - Final imtahan axını
    "final_exam_begin",
    "final_exam_cancel",
    "final_exam_entry",
    "final_exam_waiting",
    "final_ticket_state",
    # Exam Center - zallar / oturumlar / monitor / hesabat
    "exam_center_pin_lookup",
    "exam_center_pin_search",
    "exam_center_stats_ai",
    "exam_center_stats_charts",
    "exam_center_stats_data",
    "exam_center_stats_export",
    "exam_center_stats_filters",
    "stats_faculty_search",
    "stats_department_search",
    "stats_teacher_search",
    "exam_center_student_pins",
    "exam_center_reports",
    "exam_center_room_assign_invigilators",
    "exam_center_room_list",
    "exam_center_room_monitor",
    "exam_center_room_end_all",
    "exam_center_room_open_all",
    "exam_center_room_snapshot",
    "exam_center_room_start_all",
    "exam_center_attempt_violations",
    "exam_center_session_cancel",
    "exam_center_session_create",
    "exam_center_session_detail",
    "exam_center_session_end",
    "exam_center_session_history",
    "exam_center_session_list",
    "exam_center_session_monitor",
    "exam_center_session_open_entry",
    "exam_center_session_snapshot",
    "exam_center_session_start",
    "exam_center_ticket_readmit",
    "exam_center_ticket_reentry",
    "exam_center_ticket_remove",
    "exam_center_ticket_resume",
    "exam_center_ticket_seat",
    "exam_center_ticket_snapshot",
]
