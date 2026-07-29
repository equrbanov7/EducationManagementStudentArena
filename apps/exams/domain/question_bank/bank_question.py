"""exams question_bank domeni — BankQuestion/BankQuestionOption.

`upload_to`/`validators` callable-ları (question_media_path və s.) paket
`__init__`-də qalır ki, miqrasiya serializasiyası (`func.__module__`) dəyişməsin;
burada onları parent paketdən import edirik (partial-init pattern)."""

from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import pgettext_lazy

from apps.exams.constants import DEFAULT_EXAM_LANGUAGE, EXAM_LANGUAGE_CHOICES
from apps.exams.domain.question_bank import (
    User,
    bank_option_media_path,
    bank_question_media_path,
    validate_video_size,
)

from .exam_question import (
    ExamQuestion,
    ExamQuestionOption,
)


class BankQuestion(models.Model):
    """
    Kitabxana sualı — imtahandan ASILI DEYİL. Bir dəfə yaradılır, çoxlu
    imtahanda istifadə oluna bilər. İmtahana əlavə edildikdə məzmun
    ``ExamQuestion``-a kopyalanır (snapshot), beləliklə bankdakı sonrakı
    redaktələr köhnə imtahanlara təsir etmir.
    """

    ANSWER_MODE_CHOICES = ExamQuestion.ANSWER_MODE_CHOICES
    DIFFICULTY_CHOICES = ExamQuestion.DIFFICULTY_CHOICES
    QUESTION_TYPE_CHOICES = (
        ("test", pgettext_lazy("exams.model.bank_question.choice.question_type", "test")),
        ("written", pgettext_lazy("exams.model.bank_question.choice.question_type", "written")),
    )

    bank = models.ForeignKey(
        "exams.QuestionBank",
        on_delete=models.CASCADE,
        related_name="library_questions",
        verbose_name=pgettext_lazy("exams.model.bank_question.field", "bank"),
    )
    text = models.TextField(
        verbose_name=pgettext_lazy("exams.model.bank_question.field", "text"),
    )
    question_type = models.CharField(
        max_length=20,
        choices=QUESTION_TYPE_CHOICES,
        default="test",
        verbose_name=pgettext_lazy("exams.model.bank_question.field", "question_type"),
    )
    answer_mode = models.CharField(
        max_length=20,
        choices=ANSWER_MODE_CHOICES,
        default="single",
        verbose_name=pgettext_lazy("exams.model.bank_question.field", "answer_mode"),
    )
    correct_answer = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.bank_question.field", "correct_answer"),
    )
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default="medium",
        verbose_name=pgettext_lazy("exams.model.bank_question.field", "difficulty"),
    )
    language = models.CharField(
        max_length=10,
        choices=EXAM_LANGUAGE_CHOICES,
        default=DEFAULT_EXAM_LANGUAGE,
        db_index=True,
        verbose_name=pgettext_lazy("exams.model.bank_question.field", "language"),
    )
    points = models.PositiveIntegerField(default=1)
    tags = models.JSONField(
        default=list,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.bank_question.field", "tags"),
    )
    explanation = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.bank_question.field", "explanation"),
    )
    fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    image = models.ImageField(
        upload_to=bank_question_media_path,
        blank=True,
        null=True,
        verbose_name=pgettext_lazy("exams.model.bank_question.field", "image"),
    )
    image_replaces_text = models.BooleanField(default=False)
    video = models.FileField(
        upload_to=bank_question_media_path,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["mp4", "webm", "mov"]),
            validate_video_size,
        ],
        verbose_name=pgettext_lazy("exams.model.bank_question.field", "video"),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=pgettext_lazy("exams.model.bank_question.field", "is_active"),
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_library_questions",
        verbose_name=pgettext_lazy("exams.model.bank_question.field", "created_by"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.bank_question.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.bank_question.meta", "plural")
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["bank", "is_active"], name="bankq_bank_active_idx"),
            models.Index(fields=["bank", "language"], name="bankq_bank_lang_idx"),
            models.Index(fields=["bank", "difficulty"], name="bankq_bank_diff_idx"),
        ]

    def __str__(self):
        return f"{self.bank_id} · {self.text[:50]}"

    @property
    def correct_options(self):
        return self.options.filter(is_correct=True)


class BankQuestionOption(models.Model):
    LABEL_CHOICES = ExamQuestionOption.LABEL_CHOICES

    question = models.ForeignKey(
        "exams.BankQuestion",
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name=pgettext_lazy("exams.model.bank_question_option.field", "question"),
    )
    label = models.CharField(max_length=1, choices=LABEL_CHOICES, null=True, blank=True)
    text = models.TextField(
        verbose_name=pgettext_lazy("exams.model.bank_question_option.field", "text"),
    )
    # Düstur/şəkil variantları üçün (bax: ExamQuestionOption.image).
    image = models.ImageField(
        upload_to=bank_option_media_path,
        blank=True,
        null=True,
        verbose_name=pgettext_lazy("exams.model.bank_question_option.field", "image"),
    )
    image_replaces_text = models.BooleanField(default=False)
    is_correct = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.bank_question_option.field", "is_correct"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.bank_question_option.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.bank_question_option.meta", "plural")

    def __str__(self):
        prefix = "✓" if self.is_correct else "•"
        return f"{prefix} {self.text[:50]}"
