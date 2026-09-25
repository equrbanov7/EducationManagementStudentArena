"""Tapşırıqlar — sərbəst iş (ballı, jurnala düşür) və ev tapşırığı (yalnız yoxlanır).

Sərbəst iş SLOT-ları sillabusun ``self`` bölməsindən yaranır (1x10 / 2x5 / 10x1):
N slot × ``per_score`` bal. Müəllim slotun başlığını/təlimatını doldurur, amma
strukturun icazə verdiyindən ARTIQ slot yarada bilməz — DB-də aktiv slot
nömrəsi qovluq üzrə UNIKALDIR. Ev tapşırığının sayı məhdud deyil.

``lineage_key`` — tapşırığın semestrlərarası «nəsil» açarı: qovluq növbəti
semestrə köçürüləndə tapşırıq açarı saxlayır; plagiat yoxlaması keçən illərin
eyni tapşırığı ilə müqayisəni bu açarla tapır.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import DEFAULT_MAX_FILES, DEFAULT_SUBMISSION_MAX_MB, SELFWORK_TOTAL_CAP, TaskKind
from .folder import FolderTopic, SubjectFolder
from .paths import task_attachment_path

_CTX = "subject_folder.model"


class FolderTask(UUIDModel, TimeStampedModel):
    """Qovluğun bir tapşırığı."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subject_folder_tasks"
    )
    folder = models.ForeignKey(SubjectFolder, on_delete=models.CASCADE, related_name="tasks")
    topic = models.ForeignKey(FolderTopic, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks")
    kind = models.CharField(max_length=16, choices=TaskKind.choices)
    title = models.CharField(max_length=255)
    instructions = models.TextField(blank=True)
    slot_index = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Sərbəst iş slotunun nömrəsi (1-dən). Ev tapşırığında boşdur."
    )
    max_points = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Sərbəst iş slotunun maksimal balı (sillabus strukturundan). Ev tapşırığında boşdur.",
    )
    syllabus_title = models.CharField(
        max_length=255, blank=True, default="", help_text="Sillabusdakı sərbəst iş mövzusu (sinxron üçün)."
    )
    allowed_extensions = models.JSONField(
        default=list, blank=True, help_text="İcazəli fayl uzantıları; boş = modulun standart siyahısı."
    )
    max_file_mb = models.PositiveSmallIntegerField(default=DEFAULT_SUBMISSION_MAX_MB)
    max_files = models.PositiveSmallIntegerField(default=DEFAULT_MAX_FILES)
    allow_text_answer = models.BooleanField(default=True)
    allow_files = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=False, db_index=True)
    is_archived = models.BooleanField(
        default=False,
        help_text="Sillabus strukturu dəyişib və ya müəllim gizlədib — göndərişləri olan tapşırıq SİLİNMİR.",
    )
    lineage_key = models.UUIDField(default=uuid.uuid4, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "tapşırıq")
        verbose_name_plural = pgettext_lazy(_CTX, "tapşırıqlar")
        ordering = ["folder", "kind", "slot_index", "order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["folder", "slot_index"],
                condition=Q(kind=TaskKind.SELFWORK, is_archived=False),
                name="sf_task_uniq_active_selfwork_slot",
            ),
            models.CheckConstraint(
                # ⚠️ ``isnull=False`` AÇIQ yazılır: SQL CHECK-də NULL müqayisəsi NULL verir və
                # constraint-i KEÇİR (``slot_index >= 1`` NULL slotu rədd etmir).
                condition=(
                    Q(
                        kind=TaskKind.SELFWORK,
                        slot_index__isnull=False,
                        max_points__isnull=False,
                        slot_index__gte=1,
                        max_points__gt=0,
                        max_points__lte=SELFWORK_TOTAL_CAP,
                    )
                    | Q(kind=TaskKind.HOMEWORK, slot_index__isnull=True, max_points__isnull=True)
                ),
                name="sf_task_kind_shape",
            ),
            models.CheckConstraint(condition=Q(max_files__gte=1), name="sf_task_max_files_positive"),
            models.CheckConstraint(condition=Q(max_file_mb__gte=1), name="sf_task_max_file_mb_positive"),
        ]
        indexes = [
            models.Index(fields=["organization", "folder", "kind"], name="sf_task_org_folder_kind"),
        ]

    def __str__(self):
        return self.title

    @property
    def is_selfwork(self) -> bool:
        return self.kind == TaskKind.SELFWORK


class TaskAttachment(UUIDModel, TimeStampedModel):
    """Müəllimin tapşırığa qoşduğu fayl (şərt, nümunə, şablon)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subject_folder_task_attachments"
    )
    task = models.ForeignKey(FolderTask, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=task_attachment_path, max_length=255)
    original_name = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=120, blank=True, default="")
    sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "tapşırıq qoşması")
        verbose_name_plural = pgettext_lazy(_CTX, "tapşırıq qoşmaları")
        ordering = ["task", "created_at"]
        indexes = [models.Index(fields=["organization", "task"], name="sf_attachment_org_task")]

    def __str__(self):
        return self.original_name


__all__ = ["FolderTask", "TaskAttachment"]
