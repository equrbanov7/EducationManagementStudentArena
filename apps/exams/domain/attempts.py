from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.exams.validators import validate_file_extension, validate_file_size, validate_zip_contents

from .grading import AnswerGradingMixin, AttemptGradingMixin

User = get_user_model()


class ExamAttempt(AttemptGradingMixin, models.Model):
    STATUS_CHOICES = (
        ("draft", pgettext_lazy("exams.model.attempt.choice.status", "draft")),
        ("in_progress", pgettext_lazy("exams.model.attempt.choice.status", "in_progress")),
        ("submitted", pgettext_lazy("exams.model.attempt.choice.status", "submitted")),
        ("expired", pgettext_lazy("exams.model.attempt.choice.status", "expired")),
    )

    SUPERVISION_STATUS_CHOICES = (
        ("active", pgettext_lazy("exams.model.attempt.choice.supervision_status", "active")),
        ("warned", pgettext_lazy("exams.model.attempt.choice.supervision_status", "warned")),
        ("locked", pgettext_lazy("exams.model.attempt.choice.supervision_status", "locked")),
        ("removed", pgettext_lazy("exams.model.attempt.choice.supervision_status", "removed")),
        ("resumed", pgettext_lazy("exams.model.attempt.choice.supervision_status", "resumed")),
    )

    checked_by_teacher = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "checked_by_teacher"),
    )
    teacher_checked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "teacher_checked_at"),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="exam_attempts")
    exam = models.ForeignKey("exams.Exam", on_delete=models.CASCADE, related_name="attempts")
    attempt_number = models.PositiveIntegerField(
        default=1,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "attempt_number"),
        help_text=pgettext_lazy("exams.model.attempt.help", "attempt_number"),
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="in_progress",
        verbose_name=pgettext_lazy("exams.model.attempt.field", "status"),
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    duration_seconds = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "duration_seconds"),
    )
    correct_count = models.PositiveIntegerField(default=0)
    wrong_count = models.PositiveIntegerField(default=0)
    teacher_score = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "teacher_score"),
        help_text=pgettext_lazy("exams.model.attempt.help", "teacher_score"),
    )
    teacher_feedback = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "teacher_feedback"),
    )
    supervision_status = models.CharField(
        max_length=20,
        choices=SUPERVISION_STATUS_CHOICES,
        default="active",
        verbose_name=pgettext_lazy("exams.model.attempt.field", "supervision_status"),
    )
    supervision_violation_count = models.PositiveIntegerField(
        default=0,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "supervision_violation_count"),
    )
    supervision_extra_chances = models.PositiveIntegerField(
        default=0,
        verbose_name=pgettext_lazy("exams.model.attempt.field", "supervision_extra_chances"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.attempt.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.attempt.meta", "plural")
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["user", "exam", "status"]),
            models.Index(fields=["user", "exam", "-started_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} → {self.exam.title} (#{self.attempt_number})"

    @property
    def is_finished(self):
        return self.status in ("submitted", "expired")

    @property
    def deadline_at(self):
        if not self.started_at:
            return None
        duration_minutes = getattr(self.exam, "total_duration_minutes", None)
        if not duration_minutes:
            return None
        return self.started_at + timedelta(minutes=duration_minutes)

    @property
    def score_percent(self):
        total = self.correct_count + self.wrong_count
        if not total:
            return 0
        return round(self.correct_count * 100 / total, 1)

    def is_time_limit_reached(self, *, at_time=None):
        deadline = self.deadline_at
        if deadline is None:
            return False
        return (at_time or timezone.now()) >= deadline

    def expire_if_time_limit_reached(self, *, at_time=None):
        if self.is_finished or not self.is_time_limit_reached(at_time=at_time):
            return False
        self.mark_finished(status="expired")
        return True

    def mark_finished(self, status="submitted", extra_update_fields=None):
        self.status = status
        self.finished_at = timezone.now()
        if self.finished_at and self.started_at:
            delta = self.finished_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())
        update_fields = ["status", "finished_at", "duration_seconds"]
        if extra_update_fields:
            update_fields.extend(extra_update_fields)
        self.save(update_fields=list(dict.fromkeys(update_fields)))

    def recalculate_score(self):
        qs = self.answers.all()
        self.correct_count = qs.filter(is_correct=True).count()
        self.wrong_count = qs.filter(is_correct=False).count()
        self.save(update_fields=["correct_count", "wrong_count"])


class ExamAnswer(AnswerGradingMixin, models.Model):
    """
    Bir attempt daxilində konkret bir suala verilən cavab.
    Test + yazılı üçün birləşmiş model.
    """

    attempt = models.ForeignKey("exams.ExamAttempt", on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey("exams.ExamQuestion", on_delete=models.CASCADE, related_name="answers")
    selected_options = models.ManyToManyField(
        "exams.ExamQuestionOption",
        blank=True,
        related_name="selected_in_answers",
        verbose_name=pgettext_lazy("exams.model.answer.field", "selected_options"),
    )
    text_answer = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.answer.field", "text_answer"),
    )
    is_correct = models.BooleanField(
        default=False,
        verbose_name=pgettext_lazy("exams.model.answer.field", "is_correct"),
    )
    teacher_score = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name=pgettext_lazy("exams.model.answer.field", "teacher_score"),
        help_text=pgettext_lazy("exams.model.answer.help", "teacher_score"),
    )
    teacher_feedback = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("exams.model.answer.field", "teacher_feedback"),
    )
    updated_at = models.DateTimeField(auto_now=True)
    has_paint = models.BooleanField(default=False)
    paint_image = models.ImageField(upload_to="exam_paints/%Y/%m/", null=True, blank=True)
    paint_updated_at = models.DateTimeField(null=True, blank=True)
    paint_data_url = models.TextField(null=True, blank=True)

    class Meta:
        verbose_name = pgettext_lazy("exams.model.answer.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.answer.meta", "plural")
        unique_together = ("attempt", "question")

    def __str__(self):
        return f"{self.attempt} → {self.question}"


class ExamAnswerFile(models.Model):
    answer = models.ForeignKey(
        "exams.ExamAnswer",
        on_delete=models.CASCADE,
        related_name="files",
        verbose_name=pgettext_lazy("exams.model.answer_file.field", "answer"),
    )
    file = models.FileField(
        pgettext_lazy("exams.model.answer_file.field", "file"),
        upload_to="exam_uploads/",
        validators=[validate_file_extension, validate_file_size, validate_zip_contents],
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=pgettext_lazy("exams.model.answer_file.field", "uploaded_at"),
    )

    def filename(self):
        return self.file.name.split("/")[-1]

    def __str__(self):
        return f"{self.filename()} ({self.answer_id})"


class ProctoringLog(models.Model):
    EVENT_TYPE_CHOICES = (
        ("tab_switch", pgettext_lazy("exams.model.proctoring.choice.event_type", "tab_switch")),
        ("copy_paste", pgettext_lazy("exams.model.proctoring.choice.event_type", "copy_paste")),
        ("right_click", pgettext_lazy("exams.model.proctoring.choice.event_type", "right_click")),
        ("fullscreen_exit", pgettext_lazy("exams.model.proctoring.choice.event_type", "fullscreen_exit")),
        ("focus_loss", pgettext_lazy("exams.model.proctoring.choice.event_type", "focus_loss")),
        ("browser_console", pgettext_lazy("exams.model.proctoring.choice.event_type", "browser_console")),
        ("screenshot_attempt", pgettext_lazy("exams.model.proctoring.choice.event_type", "screenshot_attempt")),
        ("multiple_windows", pgettext_lazy("exams.model.proctoring.choice.event_type", "multiple_windows")),
        ("suspicious_activity", pgettext_lazy("exams.model.proctoring.choice.event_type", "suspicious_activity")),
        ("network_disconnect", pgettext_lazy("exams.model.proctoring.choice.event_type", "network_disconnect")),
        ("other", pgettext_lazy("exams.model.proctoring.choice.event_type", "other")),
    )

    exam_attempt = models.ForeignKey(
        "exams.ExamAttempt",
        on_delete=models.CASCADE,
        related_name="proctoring_logs",
        verbose_name=pgettext_lazy("exams.model.proctoring.field", "exam_attempt"),
    )
    event_type = models.CharField(
        max_length=50,
        choices=EVENT_TYPE_CHOICES,
        verbose_name=pgettext_lazy("exams.model.proctoring.field", "event_type"),
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=pgettext_lazy("exams.model.proctoring.field", "timestamp"),
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=pgettext_lazy("exams.model.proctoring.field", "details"),
        help_text=pgettext_lazy("exams.model.proctoring.help", "details"),
    )

    class Meta:
        verbose_name = pgettext_lazy("exams.model.proctoring.meta", "singular")
        verbose_name_plural = pgettext_lazy("exams.model.proctoring.meta", "plural")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["exam_attempt", "-timestamp"]),
            models.Index(fields=["event_type"]),
        ]

    def __str__(self):
        return f"{self.exam_attempt.user.username} - {self.get_event_type_display()} @ {self.timestamp}"


__all__ = [
    "ExamAnswer",
    "ExamAnswerFile",
    "ExamAttempt",
    "ProctoringLog",
]
