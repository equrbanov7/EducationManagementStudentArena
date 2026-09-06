"""Təsdiqdən sonrakı düzəlişlərin APPEND-ONLY reyestri (spec §5.7).

Bölgü ``distributed`` olandan sonra sətir/bölgü dəyişikliyi YALNIZ bu qeydlə
gedir: səbəb + qeyd MƏCBURİ, köhnə/yeni dəyər snapshot-lanır, hər qeyd
``core.audit.log_action``-a da düşür. PDF sənəd opsionaldır (org siyasəti) —
jurnal düzəlişlərindəki ``FileUploadValidator`` naxışı ilə.

Fiziki append-only qoruma Postgres trigger-i ilədir (``0002_rls_workload``);
Python qatında ``save()``/``delete()`` də bağlıdır ki, sqlite testlərində
davranış eyni olsun.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel
from core.upload_security import FileUploadValidator

from ..constants import AmendmentReason, AmendmentTarget
from .task import TeachingTask

_CTX = "workload.model"


def amendment_document_path(instance, filename):
    """Org-scoped yol: ``workload_amendments/<org_id>/<task_id>/<fayl>``."""
    return f"workload_amendments/{instance.organization_id}/{instance.task_id}/{filename}"


class WorkloadAmendment(UUIDModel, TimeStampedModel):
    """Bir düzəliş hadisəsi — DƏYİŞMƏZ (append-only)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="workload_amendments"
    )
    task = models.ForeignKey(TeachingTask, on_delete=models.CASCADE, related_name="amendments")
    target_kind = models.CharField(max_length=16, choices=AmendmentTarget.choices)
    target_id = models.UUIDField(help_text="Hədəf sətrin/bölgünün id-si (FK YOX — hədəf silinsə də qeyd qalır).")
    reason = models.CharField(max_length=32, choices=AmendmentReason.choices)
    note = models.TextField(help_text="Səbəbin açıqlaması — MƏCBURİ.")
    old_values = models.JSONField(default=dict, blank=True)
    #: Çağıranın NİYYƏT etdiyi dəyər — yalnız audit/informativ snapshot-dur.
    #: `services.amendments.open_amendment` bunu sətrə/bölgüyə TƏTBİQ ETMİR;
    #: faktiki dəyişiklik ayrı yazma çağırışı ilə edilir (bax həmin funksiyanın
    #: docstring-i).
    new_values = models.JSONField(default=dict, blank=True)
    document = models.FileField(
        upload_to=amendment_document_path,
        null=True,
        blank=True,
        validators=[FileUploadValidator(allowed_extensions={".pdf"}, max_size_mb=10)],
        help_text="Rəsmi sənəd (PDF) — org siyasəti ilə məcburi ola bilər.",
    )
    made_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="workload_amendments",
    )

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "yük düzəlişi")
        verbose_name_plural = pgettext_lazy(_CTX, "yük düzəlişləri")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task", "-created_at"]),
            models.Index(fields=["organization", "target_kind", "target_id"]),
        ]

    def __str__(self):
        return f"{self.target_kind}:{self.target_id} · {self.reason}"

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError(pgettext_lazy(_CTX, "Düzəliş qeydi dəyişdirilə bilməz (append-only reyestr)."))
        if not (self.note or "").strip():
            raise ValidationError(pgettext_lazy(_CTX, "Düzəliş üçün qeyd MƏCBURİDİR."))
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(pgettext_lazy(_CTX, "Düzəliş qeydi silinə bilməz (append-only reyestr)."))


__all__ = ["WorkloadAmendment", "amendment_document_path"]
