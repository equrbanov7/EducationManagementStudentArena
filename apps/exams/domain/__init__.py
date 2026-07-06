"""
Exam domain model slices.
"""

from .access_policy import StudentGroup
from .attempts import ExamAnswer, ExamAnswerFile, ExamAttempt, ProctoringLog
from .exam_definition import Exam, QuestionBlock
from .final_center import ExamRoom, ExamRoomSession, FinalExamTicket
from .language import ExamLanguageVariant
from .question_bank import (
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
from .submission_inbox import QuestionSubmission

__all__ = [
    "BankQuestion",
    "BankQuestionOption",
    "Exam",
    "ExamAnswer",
    "ExamAnswerFile",
    "ExamAttempt",
    "ExamLanguageVariant",
    "ExamQuestion",
    "ExamQuestionOption",
    "ExamRoom",
    "ExamRoomSession",
    "FinalExamTicket",
    "ProctoringLog",
    "QuestionBank",
    "QuestionBlock",
    "QuestionSubmission",
    "StudentGroup",
    "bank_option_media_path",
    "bank_question_media_path",
    "option_media_path",
    "question_media_path",
    "validate_video_size",
]
