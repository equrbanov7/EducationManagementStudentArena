# exams/views/student/__init__.py

from .results import (
    exam_result,
    student_exam_history,
)

from .attempts import (
    start_exam,
    take_exam,
)

from .lists import (
    assigned_student_exam_list,
    student_exam_list,
)

__all__ = [
    'exam_result',
    'student_exam_history',
    'start_exam',
    'take_exam',
    'assigned_student_exam_list',
    'student_exam_list',
]