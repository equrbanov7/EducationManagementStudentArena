"""teacher questions — geriyə-uyğun fasad paketi."""

from .bank import (  # noqa: F401
    teacher_questions_bank,
)
from .crud import (  # noqa: F401
    add_exam_question,
    delete_exam_question,
    edit_exam_question,
)

__all__ = [
    "add_exam_question",
    "delete_exam_question",
    "edit_exam_question",
    "teacher_questions_bank",
]
