"""exams question_bank domeni — geriyə-uyğun fasad paketi.

MÜHÜM: `upload_to`/`validators` callable-ları (question_media_path,
bank_question_media_path, option_media_path, bank_option_media_path,
validate_video_size) və `User` BU faylda (paket __init__) təyin olunur ki,
onların `__module__` dəyəri `apps.exams.domain.question_bank` olaraq qalsın — əks halda Django
miqrasiya serializasiyası upload_to yolunu dəyişər və saxta migration yaranar.
Modellər aşağıda import olunur (partial-init: modullar bu funksiyaları parent
paketdən götürür).
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

User = get_user_model()


def question_media_path(instance, filename):
    return f"question_media/exam_{instance.exam_id}/q_{instance.id or 'new'}/{filename}"


def bank_question_media_path(instance, filename):
    return f"bank_media/bank_{instance.bank_id}/q_{instance.id or 'new'}/{filename}"


def option_media_path(instance, filename):
    """İmtahan sualı variantının düstur şəkli üçün yol."""
    exam_id = getattr(instance.question, "exam_id", None)
    return f"question_media/exam_{exam_id}/opt_{instance.id or 'new'}/{filename}"


def bank_option_media_path(instance, filename):
    """Kitabxana sualı variantının düstur şəkli üçün yol."""
    bank_id = getattr(instance.question, "bank_id", None)
    return f"bank_media/bank_{bank_id}/opt_{instance.id or 'new'}/{filename}"


def validate_video_size(f):
    max_mb = 30
    if f.size > max_mb * 1024 * 1024:
        raise ValidationError(pgettext("exams.model.error", "video_size_exceeded").format(max_mb=max_mb))


from .bank_question import BankQuestion, BankQuestionOption  # noqa: E402,F401

# Modelləri funksiyalardan SONRA import et (partial-init sırası vacibdir).
from .exam_question import ExamQuestion, ExamQuestionOption, QuestionBank  # noqa: E402,F401

__all__ = [
    "BankQuestion",
    "BankQuestionOption",
    "ExamQuestion",
    "ExamQuestionOption",
    "QuestionBank",
    "bank_option_media_path",
    "bank_question_media_path",
    "option_media_path",
    "question_media_path",
    "validate_video_size",
]
