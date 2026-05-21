# exams/views/teacher/__init__.py

from .exams import (
    createAndEditExamView,
    delete_exam,
    teacher_exam_detail,
    teacher_exam_list,
    toggle_exam_active,
    toggle_exam_results_visibility,
)
from .groups import (
    create_student_group,
    teacher_create_group,
    teacher_delete_group,
    teacher_group_list,
    teacher_remove_student_from_group,
    teacher_update_group,
)
from .question_bank import ai_generate_question_bank, create_question_bank, process_question_bank, test_question_bank
from .questions import add_exam_question, delete_exam_question, edit_exam_question, teacher_questions_bank
from .results import (
    delete_exam_attempts,
    teacher_check_attempt,
    teacher_exam_results,
    teacher_pending_attempts,
    teacher_view_attempt,
)

__all__ = [
    "teacher_group_list",
    "teacher_create_group",
    "teacher_update_group",
    "teacher_delete_group",
    "teacher_remove_student_from_group",
    "create_student_group",
    "teacher_exam_list",
    "createAndEditExamView",
    "teacher_exam_detail",
    "toggle_exam_active",
    "toggle_exam_results_visibility",
    "delete_exam",
    "add_exam_question",
    "edit_exam_question",
    "delete_exam_question",
    "teacher_questions_bank",
    "create_question_bank",
    "process_question_bank",
    "test_question_bank",
    "ai_generate_question_bank",
    "teacher_exam_results",
    "delete_exam_attempts",
    "teacher_view_attempt",
    "teacher_check_attempt",
    "teacher_pending_attempts",
]
