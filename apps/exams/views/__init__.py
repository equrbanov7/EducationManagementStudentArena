# exams/views/__init__.py

# ═══════════════════════════════════════════════════════════════
# SHARED VIEWS (bütün user-lər üçün ortaq)
# ═══════════════════════════════════════════════════════════════
from .shared.access import exam_code_check
from .student.attempts import start_exam, take_exam
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
)

# ═══════════════════════════════════════════════════════════════
# TEACHER VIEWS
# ═══════════════════════════════════════════════════════════════
from .teacher.groups import (
    create_student_group,
    teacher_create_group,
    teacher_delete_group,
    teacher_group_list,
    teacher_update_group,
)
from .teacher.question_bank import create_question_bank, process_question_bank, test_question_bank
from .teacher.questions import add_exam_question, delete_exam_question, edit_exam_question
from .teacher.results import teacher_check_attempt, teacher_exam_results, teacher_pending_attempts, teacher_view_attempt

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
    # Teacher - Exams
    "teacher_exam_list",
    "createAndEditExamView",
    "teacher_exam_detail",
    "toggle_exam_active",
    "delete_exam",
    # Teacher - Questions
    "add_exam_question",
    "edit_exam_question",
    "delete_exam_question",
    # Teacher - Question Bank
    "create_question_bank",
    "process_question_bank",
    "test_question_bank",
    # Teacher - Results
    "teacher_exam_results",
    "teacher_view_attempt",
    "teacher_check_attempt",
    "teacher_pending_attempts",
    # Student - Results
    "exam_result",
    "student_exam_history",
    # Student - Attempts
    "start_exam",
    "take_exam",
    # Student - Lists
    "assigned_student_exam_list",
    "student_exam_list",
]
