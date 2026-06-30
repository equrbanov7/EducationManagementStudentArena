"""question_bank paketi — köhnə teacher/question_bank.py-nin geriyə-uyğun fasadı."""

from apps.exams.services.ai_question_generation import generate_question_bank_text  # noqa: F401

from ._reports import _build_question_bank_report_xlsx  # noqa: F401
from ._views_create import (  # noqa: F401
    ai_generate_question_bank,
    create_question_bank,
    process_question_bank,
)
from ._views_misc import (  # noqa: F401
    exam_questions_word_export,
    test_question_bank,
    test_question_bank_template_download,
)

__all__ = [
    "ai_generate_question_bank",
    "create_question_bank",
    "exam_questions_word_export",
    "process_question_bank",
    "test_question_bank",
    "test_question_bank_template_download",
    "_build_question_bank_report_xlsx",
    "generate_question_bank_text",
]
