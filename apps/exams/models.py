"""
Compatibility shim for the exams domain models.

The concrete model definitions live under ``apps.exams.domain`` so the exam
domain can be maintained in smaller slices without breaking existing imports
or migration references that still point at ``apps.exams.models``.
"""

from apps.exams.domain.access_policy import StudentGroup
from apps.exams.domain.ai_config import AIConfiguration
from apps.exams.domain.attempts import ExamAnswer, ExamAnswerFile, ExamAttempt, ProctoringLog
from apps.exams.domain.coding import CodingExamQuestion, CodingFile, CodingSubmission, CodingTestCase
from apps.exams.domain.exam_definition import Exam, QuestionBlock
from apps.exams.domain.import_jobs import TextExtractionJob, extraction_job_upload_path
from apps.exams.domain.language import ExamLanguageVariant
from apps.exams.domain.question_bank import (
    BankQuestion,
    BankQuestionOption,
    ExamQuestion,
    ExamQuestionOption,
    QuestionBank,
    bank_option_media_path,
    bank_question_media_path,
    option_media_path,
    question_media_path,
    validate_video_size,
)
from apps.exams.domain.supervision import ExamSupervisionConfig, SupervisionIncident

__all__ = [
    "AIConfiguration",
    "TextExtractionJob",
    "extraction_job_upload_path",
    "BankQuestion",
    "BankQuestionOption",
    "CodingExamQuestion",
    "CodingFile",
    "CodingSubmission",
    "CodingTestCase",
    "Exam",
    "ExamAnswer",
    "ExamAnswerFile",
    "ExamAttempt",
    "ExamLanguageVariant",
    "ExamQuestion",
    "ExamQuestionOption",
    "ExamSupervisionConfig",
    "ProctoringLog",
    "QuestionBank",
    "QuestionBlock",
    "StudentGroup",
    "SupervisionIncident",
    "bank_option_media_path",
    "bank_question_media_path",
    "option_media_path",
    "question_media_path",
    "validate_video_size",
]
