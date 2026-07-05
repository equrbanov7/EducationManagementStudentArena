# exams/views/student/__init__.py

from .attempts import start_exam, take_exam
from .lists import assigned_student_exam_list, final_exam_list, student_exam_list
from .results import exam_result, student_exam_history

__all__ = [
    "exam_result",
    "student_exam_history",
    "start_exam",
    "take_exam",
    "assigned_student_exam_list",
    "final_exam_list",
    "student_exam_list",
]
