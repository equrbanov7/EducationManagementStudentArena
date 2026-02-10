# exams/views/teacher/__init__.py

from .groups import (
    teacher_group_list,
    teacher_create_group,
    teacher_update_group,
    teacher_delete_group,
    create_student_group,
)

from .exams import (
    teacher_exam_list,
    createAndEditExamView,
    teacher_exam_detail,
    toggle_exam_active,
    delete_exam,
)

from .questions import (
    add_exam_question,
    edit_exam_question,
    delete_exam_question,
)

from .question_bank import (
    create_question_bank,
    process_question_bank,
    test_question_bank,
)

from .results import (
    teacher_exam_results,
    teacher_view_attempt,
    teacher_check_attempt,
    teacher_pending_attempts,
)

__all__ = [
    'teacher_group_list',
    'teacher_create_group',
    'teacher_update_group',
    'teacher_delete_group',
    'create_student_group',
    'teacher_exam_list',
    'createAndEditExamView',
    'teacher_exam_detail',
    'toggle_exam_active',
    'delete_exam',
    'add_exam_question',
    'edit_exam_question',
    'delete_exam_question',
    'create_question_bank',
    'process_question_bank',
    'test_question_bank',
    'teacher_exam_results',
    'teacher_view_attempt',
    'teacher_check_attempt',
    'teacher_pending_attempts',
]