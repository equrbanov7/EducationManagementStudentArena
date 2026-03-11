"""
Compatibility shim for the exams domain models.

The concrete model definitions live under ``apps.exams.domain`` so the exam
domain can be maintained in smaller slices without breaking existing imports
or migration references that still point at ``apps.exams.models``.
"""

from apps.exams.domain.access_policy import StudentGroup
from apps.exams.domain.attempts import ExamAnswer, ExamAnswerFile, ExamAttempt, ProctoringLog
from apps.exams.domain.exam_definition import Exam, QuestionBlock
from apps.exams.domain.question_bank import (
    ExamQuestion,
    ExamQuestionOption,
    QuestionBank,
    question_media_path,
    validate_video_size,
)

__all__ = [
    "Exam",
    "ExamAnswer",
    "ExamAnswerFile",
    "ExamAttempt",
    "ExamQuestion",
    "ExamQuestionOption",
    "ProctoringLog",
    "QuestionBank",
    "QuestionBlock",
    "StudentGroup",
    "question_media_path",
    "validate_video_size",
]
