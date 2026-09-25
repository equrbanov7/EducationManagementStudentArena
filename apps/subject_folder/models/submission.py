"""Tələbə göndərişləri (cəhd zənciri), faylları və append-only tarixçəsi.

ZƏNCİR: bir (tapşırıq, qeydiyyat) cütü üçün cəhdlər ``attempt_no`` = 1, 2, …
sətirləridir. Eyni anda YALNIZ BİR cari cəhd (``is_current``) olur; müəllim
qaytaranda (``returned``) tələbə yeni cəhd açır, köhnə sətir tarixçədə qalır.

DB invariantları (CheckConstraint / partial UNIQUE):
  * bal yalnız ``accepted`` sətirdə olur və ``0 < points ≤ points_max``;
    qaytarma/rədd/yoxlama HEÇ VAXT bal yazmır («0 düşmür»);
  * ``accepted`` yalnız sərbəst iş, ``checked`` yalnız ev tapşırığı;
  * zəncirdə YALNIZ BİR yekun (accepted/checked/rejected) — ikinci bal verilmir;
  * cəm ≤ 10 (qeydiyyat üzrə bütün sərbəst işlər) — servis kilidi + 0003
    miqrasiyasının PG trigger-i (ikinci qat).
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import (
    SELFWORK_TOTAL_CAP,
    EventKind,
    JournalSyncStatus,
    PlagiarismStatus,
    RejectReason,
    SubmissionStatus,
    TaskKind,
)
from .assignment import FolderAssignment
from .paths import submission_file_path
from .tasks import FolderTask

_CTX = "subject_folder.model"
_FINAL = [SubmissionStatus.ACCEPTED, SubmissionStatus.CHECKED, SubmissionStatus.REJECTED]


class Submission(UUIDModel, TimeStampedModel):
    """Bir tapşırıq üzrə bir cəhd."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subject_folder_submissions"
    )
    task = models.ForeignKey(FolderTask, on_delete=models.PROTECT, related_name="submissions")
    assignment = models.ForeignKey(FolderAssignment, on_delete=models.PROTECT, related_name="submissions")
    enrollment = models.ForeignKey(
        "registrar.Enrollment", on_delete=models.PROTECT, related_name="subject_folder_submissions"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="subject_folder_submissions"
    )
    kind = models.CharField(max_length=16, choices=TaskKind.choices, help_text="Tapşırığın növü (snapshot).")
    attempt_no = models.PositiveSmallIntegerField(default=1)
    is_current = models.BooleanField(default=True)
    status = models.CharField(
        max_length=16, choices=SubmissionStatus.choices, default=SubmissionStatus.DRAFT, db_index=True
    )
    text_answer = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_late = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reviewer_name = models.CharField(max_length=200, blank=True, default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    feedback = models.TextField(blank=True, default="")
    reject_reason = models.CharField(max_length=16, choices=RejectReason.choices, blank=True, default="")
    points = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    points_max = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    journal_sync_status = models.CharField(
        max_length=16, choices=JournalSyncStatus.choices, default=JournalSyncStatus.NONE, db_index=True
    )
    journal_sync_message = models.CharField(max_length=500, blank=True, default="")
    journal_synced_at = models.DateTimeField(null=True, blank=True)
    journal_sync_attempts = models.PositiveSmallIntegerField(default=0)
    content_sha256 = models.CharField(
        max_length=64, blank=True, default="", db_index=True, help_text="Normallaşdırılmış mətn + fayl heşləri."
    )
    plagiarism_status = models.CharField(
        max_length=16, choices=PlagiarismStatus.choices, default=PlagiarismStatus.PENDING
    )
    similarity_max = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    plagiarism_flagged = models.BooleanField(default=False, db_index=True)
    teacher_notified_at = models.DateTimeField(null=True, blank=True)

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "göndəriş")
        verbose_name_plural = pgettext_lazy(_CTX, "göndərişlər")
        ordering = ["-submitted_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["task", "enrollment", "attempt_no"], name="sf_submission_uniq_attempt"),
            models.UniqueConstraint(
                fields=["task", "enrollment"], condition=Q(is_current=True), name="sf_submission_one_current"
            ),
            # «İkinci bal yoxdur»: zəncirdə yalnız BİR yekun sətir (qəbul/yoxlama/rədd).
            models.UniqueConstraint(
                fields=["task", "enrollment"], condition=Q(status__in=_FINAL), name="sf_submission_one_final"
            ),
            models.CheckConstraint(condition=Q(attempt_no__gte=1), name="sf_submission_attempt_positive"),
            models.CheckConstraint(
                condition=Q(points__isnull=True) | Q(status=SubmissionStatus.ACCEPTED),
                name="sf_submission_points_only_when_accepted",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(status=SubmissionStatus.ACCEPTED)
                    | Q(kind=TaskKind.SELFWORK, points__isnull=False, points_max__isnull=False)
                ),
                name="sf_submission_accepted_is_scored_selfwork",
            ),
            models.CheckConstraint(
                condition=Q(points__isnull=True)
                | (Q(points_max__isnull=False) & Q(points__gt=0) & Q(points__lte=F("points_max"))),
                name="sf_submission_points_range",
            ),
            models.CheckConstraint(
                condition=Q(points_max__isnull=True) | Q(points_max__lte=SELFWORK_TOTAL_CAP),
                name="sf_submission_points_max_cap",
            ),
            models.CheckConstraint(
                condition=~Q(status=SubmissionStatus.CHECKED) | Q(kind=TaskKind.HOMEWORK),
                name="sf_submission_checked_is_homework",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "assignment", "status"], name="sf_sub_org_assignment_status"),
            models.Index(fields=["organization", "task", "status"], name="sf_sub_org_task_status"),
            models.Index(fields=["enrollment", "kind", "status"], name="sf_sub_enrollment_kind_status"),
            models.Index(fields=["organization", "student", "-submitted_at"], name="sf_sub_org_student"),
            models.Index(fields=["organization", "journal_sync_status"], name="sf_sub_org_journal_sync"),
        ]

    def __str__(self):
        return f"{self.task_id} · {self.enrollment_id} #{self.attempt_no}"


class SubmissionFile(UUIDModel, TimeStampedModel):
    """Göndərişə qoşulmuş fayl — ``sha256`` eyni faylın plagiat yoxlaması üçündür."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subject_folder_submission_files"
    )
    submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="files")
    file = models.FileField(upload_to=submission_file_path, max_length=255)
    original_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=120, blank=True, default="")
    sha256 = models.CharField(max_length=64, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "göndəriş faylı")
        verbose_name_plural = pgettext_lazy(_CTX, "göndəriş faylları")
        ordering = ["submission", "created_at"]
        indexes = [models.Index(fields=["organization", "sha256"], name="sf_subfile_org_sha")]

    def __str__(self):
        return self.original_name


class SubmissionEvent(UUIDModel, TimeStampedModel):
    """Göndərişin APPEND-ONLY tarixçəsi (kim, nə vaxt, nə etdi).

    Model səviyyəsində yenilənmə/silmə qadağandır; PG-də UPDATE trigger ilə
    bloklanır (0003 miqrasiyası).
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subject_folder_submission_events"
    )
    submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=24, choices=EventKind.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    actor_name = models.CharField(max_length=200, blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "göndəriş hadisəsi")
        verbose_name_plural = pgettext_lazy(_CTX, "göndəriş hadisələri")
        ordering = ["created_at"]
        indexes = [models.Index(fields=["organization", "submission", "created_at"], name="sf_event_org_sub")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Submission events are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Submission events cannot be deleted.")

    def __str__(self):
        return f"{self.submission_id} · {self.kind}"


__all__ = ["Submission", "SubmissionEvent", "SubmissionFile"]
