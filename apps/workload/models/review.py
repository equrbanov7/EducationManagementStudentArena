"""Təsdiq zəncirinin modelləri — F2 + müəllim etirazı (spec §5.3–§5.4, ekran 13/15/16).

Modul sərhədi: ``apps.*`` importu YOXDUR — cross-app FK-lər STRING label ilə
(``"organizations.OrgUnit"``), ``models/task.py`` naxışı.

Üç model, üç fərqli ömür:

* :class:`TaskFacultySlice` — tapşırığın BİR fakültəyə düşən dilimi. Hər
  ``revision``-da təzələnir (unikal ``(task, faculty, revision)``), yəni dekan
  qaytarıb yenidən göndəriləndə köhnə qərar TARİXÇƏ kimi qalır, silinmir.
* :class:`TaskRowReview` — koordinatorun sətir vizası. Bir koordinator bir
  sətrə bir dəfə rəy verir (unikal ``(row, coordinator)``); rəy dəyişəndə eyni
  sətir yenilənir, çünki «viza» cari vəziyyətdir, tarixçə deyil (tarixçə
  ``core.audit``-dədir).
* :class:`LoadObjection` — müəllimin etirazı. **Append-only** (``0005`` DB
  trigger-i): mətn heç vaxt redaktə olunmur; kafedra müdiri yalnız ``status``
  və ``resolution_note`` sahələrini bağlaya bilər (trigger həmin UPDATE-i
  ayrıca icazə verir).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import ObjectionReason, ObjectionStatus, RowReviewStatus, SliceStatus
from .assignment import TeacherAssignment
from .task import TeachingTask, TeachingTaskRow

_CTX = "workload.model"


class TaskFacultySlice(UUIDModel, TimeStampedModel):
    """Tapşırığın bir fakültəyə düşən təsdiq dilimi (spec §4.2, §5.3).

    Niyə dilim? Bir kafedranın tapşırığında BAŞQA fakültələrin ixtisasları da
    olur (xidməti tədris) — ona görə təsdiq sənəd-səviyyə deyil, fakültə
    səviyyəsindədir. Sənəd yalnız BÜTÜN dilimlər təsdiqlənəndə ``approved``
    olur (``services.workflow.recompute_task_status``).
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="workload_slices"
    )
    task = models.ForeignKey(TeachingTask, on_delete=models.CASCADE, related_name="slices")
    faculty = models.ForeignKey(
        "organizations.OrgUnit",
        on_delete=models.PROTECT,
        related_name="workload_slices",
        help_text="Fakültə (OrgUnit: faculty) — sətrin ixtisasının path-ından törəyir.",
    )
    revision = models.PositiveIntegerField(default=0, help_text="Tapşırığın göndərmə dövrü (task.revision).")
    status = models.CharField(max_length=16, choices=SliceStatus.choices, default=SliceStatus.PENDING, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decided_workload_slices",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True, help_text="Qaytarma səbəbi / təsdiq qeydi (≥20 simvol, auditli).")

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "fakültə təsdiq dilimi")
        verbose_name_plural = pgettext_lazy(_CTX, "fakültə təsdiq dilimləri")
        ordering = ["task", "faculty__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["task", "faculty", "revision"],
                name="uniq_workload_slice_task_faculty_revision",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["faculty", "status"]),
        ]

    def __str__(self):
        return f"{self.task_id} · {self.faculty_id} · {self.status}"

    @property
    def is_decided(self) -> bool:
        return self.status != SliceStatus.PENDING


class TaskRowReview(UUIDModel, TimeStampedModel):
    """Proqram koordinatorunun sətir vizası (spec §5.4, ekran 13).

    ⚠️ QAYDA (handoff §5/13): **irad yazılan sətrin ``reviewed`` bayrağı
    silinir** — sətir eyni anda həm vizalanmış, həm iradlı ola bilməz. Servis
    (``services.reviews.set_row_review``) bunu ATOMIK edir və sətrin
    ``TeachingTaskRow.review_status`` güzgüsünü də yeniləyir.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="workload_row_reviews"
    )
    row = models.ForeignKey(TeachingTaskRow, on_delete=models.CASCADE, related_name="reviews")
    coordinator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workload_row_reviews"
    )
    status = models.CharField(
        max_length=16,
        choices=[
            (RowReviewStatus.REVIEWED, RowReviewStatus.REVIEWED.label),
            (RowReviewStatus.FLAGGED, RowReviewStatus.FLAGGED.label),
        ],
        db_index=True,
    )
    comment = models.TextField(blank=True, help_text="İradda MƏCBURİ (≥20 simvol); vizada boş ola bilər.")

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "sətir vizası")
        verbose_name_plural = pgettext_lazy(_CTX, "sətir vizaları")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["row", "coordinator"], name="uniq_workload_row_review"),
        ]
        indexes = [models.Index(fields=["organization", "status"])]

    def __str__(self):
        return f"{self.row_id} · {self.status}"


class LoadObjection(UUIDModel, TimeStampedModel):
    """Müəllimin öz yükünə etirazı — APPEND-ONLY reyestr (ekran 16).

    Müəllim ya yükü TƏSDİQLƏYİR (``TeacherAssignment`` üzərində iz qalmır —
    təsdiq audit yazısıdır), ya da 4 səbəbdən biri ilə etiraz göndərir. Etiraz
    mətni heç vaxt dəyişmir; kafedra müdiri yalnız qərar sahələrini bağlayır.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="workload_objections"
    )
    row = models.ForeignKey(TeachingTaskRow, on_delete=models.CASCADE, related_name="objections")
    assignment = models.ForeignKey(
        TeacherAssignment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="objections",
        help_text="Konkret bölgü sətri (varsa) — müəllim hansı təyinata etiraz edir.",
    )
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workload_objections")
    reason_key = models.CharField(max_length=16, choices=ObjectionReason.choices, db_index=True)
    text = models.TextField(help_text="İzah (≥20 simvol).")
    status = models.CharField(
        max_length=16, choices=ObjectionStatus.choices, default=ObjectionStatus.OPEN, db_index=True
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_workload_objections",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "yük etirazı")
        verbose_name_plural = pgettext_lazy(_CTX, "yük etirazları")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["row", "teacher"]),
        ]

    def __str__(self):
        return f"{self.teacher_id} · {self.reason_key}"


__all__ = ["LoadObjection", "TaskFacultySlice", "TaskRowReview"]
