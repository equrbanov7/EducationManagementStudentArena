"""
Apellyasiya domeni.

- ``Appeal``          — bir imtahan attempt-i üzrə apellyasiya başlığı.
- ``AppealItem``      — apellyasiya edilən HƏR sual üçün ayrıca yazı (öz tipi,
                        şərhi və statusu ilə).
- ``ScoreAdjustment`` — qəbul olunmuş apellyasiya nəticəsində bal düzəlişinin
                        audit qeydi. ``AppealItem`` ilə OneToOne olduğundan
                        eyni apellyasiya üçün bal İKİ DƏFƏ artırıla bilmir
                        (idempotentlik).
"""

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from .constants import (
    APPEAL_ITEM_STATUS_CHOICES,
    APPEAL_ITEM_STATUS_PENDING,
    APPEAL_STATUS_CHOICES,
    APPEAL_STATUS_PENDING,
    APPEAL_TYPE_CHOICES,
)

User = settings.AUTH_USER_MODEL


class Appeal(models.Model):
    """Bir imtahan attempt-i üzrə student apellyasiyasının başlığı."""

    attempt = models.ForeignKey(
        "exams.ExamAttempt",
        on_delete=models.CASCADE,
        related_name="appeals",
        verbose_name=pgettext_lazy("appeals.model.appeal.field", "attempt"),
    )
    # Denormallaşdırılmış sahələr — sürətli filtr/qruplaşma üçün.
    exam = models.ForeignKey(
        "exams.Exam",
        on_delete=models.CASCADE,
        related_name="appeals",
        verbose_name=pgettext_lazy("appeals.model.appeal.field", "exam"),
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="exam_appeals",
        verbose_name=pgettext_lazy("appeals.model.appeal.field", "student"),
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="exam_appeals",
        verbose_name=pgettext_lazy("appeals.model.appeal.field", "organization"),
    )
    # Faculty/department səviyyəli scope (gələcək rollar üçün hazır).
    org_unit = models.ForeignKey(
        "organizations.OrgUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exam_appeals",
        verbose_name=pgettext_lazy("appeals.model.appeal.field", "org_unit"),
    )
    status = models.CharField(
        max_length=20,
        choices=APPEAL_STATUS_CHOICES,
        default=APPEAL_STATUS_PENDING,
        db_index=True,
        verbose_name=pgettext_lazy("appeals.model.appeal.field", "status"),
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_appeals",
        verbose_name=pgettext_lazy("appeals.model.appeal.field", "reviewed_by"),
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("appeals.model.appeal.field", "reviewed_at"),
    )
    reviewer_note = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("appeals.model.appeal.field", "reviewer_note"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("appeals.model.appeal.meta", "singular")
        verbose_name_plural = pgettext_lazy("appeals.model.appeal.meta", "plural")
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["organization", "status", "-created_at"], name="appeal_org_status_idx"),
            models.Index(fields=["exam", "status"], name="appeal_exam_status_idx"),
            models.Index(fields=["student", "-created_at"], name="appeal_student_created_idx"),
        ]

    def __str__(self):
        return f"Appeal#{self.pk} · attempt={self.attempt_id} · {self.status}"


class AppealItem(models.Model):
    """Apellyasiya edilən bir sual — öz tipi, şərhi və statusu ilə."""

    appeal = models.ForeignKey(
        "appeals.Appeal",
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=pgettext_lazy("appeals.model.item.field", "appeal"),
    )
    question = models.ForeignKey(
        "exams.ExamQuestion",
        on_delete=models.CASCADE,
        related_name="appeal_items",
        verbose_name=pgettext_lazy("appeals.model.item.field", "question"),
    )
    # Hansı cavaba aiddir (varsa). Cavab silinsə apellyasiya qalır.
    answer = models.ForeignKey(
        "exams.ExamAnswer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appeal_items",
        verbose_name=pgettext_lazy("appeals.model.item.field", "answer"),
    )
    appeal_type = models.CharField(
        max_length=30,
        choices=APPEAL_TYPE_CHOICES,
        verbose_name=pgettext_lazy("appeals.model.item.field", "appeal_type"),
    )
    # Minimum uzunluq (APPEAL_MIN_COMMENT_LENGTH) form/clean səviyyəsində
    # tətbiq olunur — DB səviyyəsində məhdudiyyət qoyulmur.
    comment = models.TextField(
        verbose_name=pgettext_lazy("appeals.model.item.field", "comment"),
    )
    status = models.CharField(
        max_length=20,
        choices=APPEAL_ITEM_STATUS_CHOICES,
        default=APPEAL_ITEM_STATUS_PENDING,
        db_index=True,
        verbose_name=pgettext_lazy("appeals.model.item.field", "status"),
    )
    reviewer_response = models.TextField(
        blank=True,
        verbose_name=pgettext_lazy("appeals.model.item.field", "reviewer_response"),
    )
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_appeal_items",
        verbose_name=pgettext_lazy("appeals.model.item.field", "resolved_by"),
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=pgettext_lazy("appeals.model.item.field", "resolved_at"),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = pgettext_lazy("appeals.model.item.meta", "singular")
        verbose_name_plural = pgettext_lazy("appeals.model.item.meta", "plural")
        ordering = ["id"]
        constraints = [
            # Eyni apellyasiyada eyni sual təkrar apellyasiya edilə bilməz.
            models.UniqueConstraint(fields=["appeal", "question"], name="appeal_item_unique_question"),
        ]
        indexes = [
            models.Index(fields=["appeal", "status"], name="appeal_item_status_idx"),
        ]

    def __str__(self):
        return f"AppealItem#{self.pk} · q={self.question_id} · {self.status}"


class ScoreAdjustment(models.Model):
    """
    Qəbul olunmuş apellyasiya nəticəsində bal düzəlişinin audit qeydi.

    ``appeal_item`` ilə OneToOne olduğu üçün eyni apellyasiya item-i üçün bal
    yalnız BİR DƏFƏ tətbiq oluna bilər — ikiqat artımın qarşısı alınır.
    """

    appeal_item = models.OneToOneField(
        "appeals.AppealItem",
        on_delete=models.CASCADE,
        related_name="score_adjustment",
        verbose_name=pgettext_lazy("appeals.model.adjustment.field", "appeal_item"),
    )
    attempt = models.ForeignKey(
        "exams.ExamAttempt",
        on_delete=models.CASCADE,
        related_name="score_adjustments",
        verbose_name=pgettext_lazy("appeals.model.adjustment.field", "attempt"),
    )
    question = models.ForeignKey(
        "exams.ExamQuestion",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="score_adjustments",
        verbose_name=pgettext_lazy("appeals.model.adjustment.field", "question"),
    )
    delta_points = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        default=0,
        verbose_name=pgettext_lazy("appeals.model.adjustment.field", "delta_points"),
    )
    previous_is_correct = models.BooleanField(null=True, blank=True)
    new_is_correct = models.BooleanField(null=True, blank=True)
    previous_score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    new_score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    # Written/coding üçün: qəbuldan əvvəlki cavab balı (answer.teacher_score).
    # Revert zamanı dəqiq bərpa üçün saxlanılır (test üçün null).
    previous_answer_score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    applied_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applied_score_adjustments",
        verbose_name=pgettext_lazy("appeals.model.adjustment.field", "applied_by"),
    )
    applied_at = models.DateTimeField(auto_now_add=True)
    reverted = models.BooleanField(default=False)

    class Meta:
        verbose_name = pgettext_lazy("appeals.model.adjustment.meta", "singular")
        verbose_name_plural = pgettext_lazy("appeals.model.adjustment.meta", "plural")
        ordering = ["-applied_at", "id"]
        indexes = [
            models.Index(fields=["attempt"], name="score_adj_attempt_idx"),
        ]

    def __str__(self):
        return f"ScoreAdjustment#{self.pk} · item={self.appeal_item_id} · Δ{self.delta_points}"


__all__ = [
    "Appeal",
    "AppealItem",
    "ScoreAdjustment",
]
