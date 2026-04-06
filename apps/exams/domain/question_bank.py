from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils.translation import pgettext, pgettext_lazy

User = get_user_model()


def question_media_path(instance, filename):
    return f"question_media/exam_{instance.exam_id}/q_{instance.id or 'new'}/{filename}"


question_media_path.__module__ = "apps.exams.models"


def validate_video_size(f):
    max_mb = 30
    if f.size > max_mb * 1024 * 1024:
        raise ValidationError(pgettext("exams.model.error", "video_size_exceeded").format(max_mb=max_mb))


validate_video_size.__module__ = "apps.exams.models"


class QuestionBank(models.Model):
    ORGANIZATION_TYPE_CHOICES = (
        ("university", pgettext_lazy("exams.model.question_bank.choice.organization_type", "university")),
        ("school", pgettext_lazy("exams.model.question_bank.choice.organization_type", "school")),
        ("course_center", pgettext_lazy("exams.model.question_bank.choice.organization_type", "course_center")),
        ("individual", pgettext_lazy("exams.model.question_bank.choice.organization_type", "individual")),
    )

    name = models.CharField(
        max_length=255,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "name"),
    )
    description = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "description"),
    )
    subject = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "subject"),
        help_text=pgettext_lazy("exams.model.question_bank.help", "subject"),
    )
    organization_type = models.CharField(
        max_length=50,
        choices=ORGANIZATION_TYPE_CHOICES,
        default="individual",
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "organization_type"),
    )
    is_shared = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "is_shared"),
        help_text=pgettext_lazy("exams.model.question_bank.help", "is_shared"),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "is_active"),
        db_index=True,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="question_banks",
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "created_by"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "created_at"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=pgettext_lazy("exams.model.question_bank.field", "updated_at"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.question_bank.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.question_bank.meta", "plural")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_by", "-created_at"]),
            models.Index(fields=["is_active", "is_shared"]),
        ]

    def __str__(self):
        return self.name

    @property
    def question_count(self):
        return self.bank_questions.count()


class ExamQuestion(models.Model):
    ANSWER_MODE_CHOICES = (
        ("single", pgettext_lazy("exams.model.question.choice.answer_mode", "single")),
        ("multiple", pgettext_lazy("exams.model.question.choice.answer_mode", "multiple")),
    )
    DIFFICULTY_CHOICES = (
        ("easy", pgettext_lazy("exams.model.question.choice.difficulty", "easy")),
        ("medium", pgettext_lazy("exams.model.question.choice.difficulty", "medium")),
        ("hard", pgettext_lazy("exams.model.question.choice.difficulty", "hard")),
    )

    points = models.PositiveIntegerField(default=1)
    fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    exam = models.ForeignKey(
        "exams.Exam",
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name=pgettext_lazy("exams.model.question.field", "exam"),
    )
    block = models.ForeignKey(
        "exams.QuestionBlock",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
        verbose_name=pgettext_lazy("exams.model.question.field", "block"),
    )
    bank = models.ForeignKey(
        "exams.QuestionBank",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_questions",
        verbose_name=pgettext_lazy("exams.model.question.field", "bank"),
        help_text=pgettext_lazy("exams.model.question.help", "bank"),
    )
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default="medium",
        verbose_name=pgettext_lazy("exams.model.question.field", "difficulty"),
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.question.field", "tags"),
        help_text=pgettext_lazy("exams.model.question.help", "tags"),
    )
    explanation = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.question.field", "explanation"),
        help_text=pgettext_lazy("exams.model.question.help", "explanation"),
    )
    usage_count = models.PositiveIntegerField(
        default=0,
        verbose_name=pgettext_lazy("exams.model.question.field", "usage_count"),
        help_text=pgettext_lazy("exams.model.question.help", "usage_count"),
    )
    text = models.TextField(
        verbose_name=pgettext_lazy("exams.model.question.field", "text"),
    )
    correct_answer = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.question.field", "correct_answer"),
    )
    order = models.PositiveIntegerField(
        default=1,
        verbose_name=pgettext_lazy("exams.model.question.field", "order"),
    )
    answer_mode = models.CharField(
        pgettext_lazy("exams.model.question.field", "answer_mode"),
        max_length=20,
        choices=ANSWER_MODE_CHOICES,
        default="single",
        help_text=pgettext_lazy("exams.model.question.help", "answer_mode"),
    )
    time_limit_seconds = models.PositiveIntegerField(
        pgettext_lazy("exams.model.question.field", "time_limit_seconds"),
        blank=True,
        null=True,
        help_text=pgettext_lazy("exams.model.question.help", "time_limit_seconds"),
    )
    image = models.ImageField(
        upload_to=question_media_path,
        blank=True,
        null=True,
        verbose_name=pgettext_lazy("exams.model.question.field", "image"),
    )
    video = models.FileField(
        pgettext_lazy("exams.model.question.field", "video"),
        upload_to=question_media_path,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=["mp4", "webm", "mov"]),
            validate_video_size,
        ],
    )
    enable_paint = models.BooleanField(
        default=False,
        help_text=pgettext_lazy("exams.model.question.help", "enable_paint"),
    )
    disable_paint = models.BooleanField(
        default=False,
        help_text=pgettext_lazy("exams.model.question.help", "disable_paint"),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=pgettext_lazy("exams.model.question.field", "is_active"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=pgettext_lazy("exams.model.question.field", "created_at"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.question.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.question.meta", "plural")
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.exam.title} – {self.order}. sual"

    @property
    def effective_time_limit(self):
        if self.time_limit_seconds:
            return self.time_limit_seconds
        if self.exam.default_question_time_seconds:
            return self.exam.default_question_time_seconds
        return None

    @property
    def total_answers(self):
        return self.answers.count()

    @property
    def correct_answers_count(self):
        return self.answers.filter(is_correct=True).count()

    @property
    def wrong_answers_count(self):
        return self.answers.filter(is_correct=False).count()

    @property
    def correct_ratio(self):
        total = self.total_answers
        if not total:
            return 0
        return round(self.correct_answers_count * 100 / total, 1)

    @property
    def inherited_paint_enabled(self):
        block = getattr(self, "block", None)
        if block is not None and block.enable_paint is not None:
            return bool(block.enable_paint)
        exam = getattr(self, "exam", None)
        return bool(getattr(exam, "enable_paint", False))

    @property
    def paint_enabled_effective(self):
        if self.disable_paint:
            return False
        if self.enable_paint:
            return True
        return self.inherited_paint_enabled

    @property
    def paint_priority_source(self):
        if self.disable_paint or self.enable_paint:
            return "question"
        block = getattr(self, "block", None)
        if block is not None and block.enable_paint is not None:
            return "block"
        return "exam"

    def set_paint_enabled(self, enabled):
        desired = bool(enabled)
        inherited_enabled = self.inherited_paint_enabled

        if desired == inherited_enabled:
            self.enable_paint = False
            self.disable_paint = False
        elif desired:
            self.enable_paint = True
            self.disable_paint = False
        else:
            self.enable_paint = False
            self.disable_paint = True


class ExamQuestionOption(models.Model):
    LABEL_CHOICES = (
        ("A", "A"),
        ("B", "B"),
        ("C", "C"),
        ("D", "D"),
        ("E", "E"),
    )

    label = models.CharField(max_length=1, choices=LABEL_CHOICES, null=True, blank=True)
    question = models.ForeignKey(
        "exams.ExamQuestion",
        on_delete=models.CASCADE,
        related_name="options",
        verbose_name=pgettext_lazy("exams.model.question_option.field", "question"),
    )
    text = models.CharField(
        max_length=255,
        verbose_name=pgettext_lazy("exams.model.question_option.field", "text"),
    )
    is_correct = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.question_option.field", "is_correct"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.question_option.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.question_option.meta", "plural")

    def __str__(self):
        prefix = "✓" if self.is_correct else "•"
        return f"{prefix} {self.text[:50]}"


__all__ = [
    "ExamQuestion",
    "ExamQuestionOption",
    "QuestionBank",
    "question_media_path",
    "validate_video_size",
]
