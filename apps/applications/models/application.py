"""Müraciətin özü — bir sətir, bir zaman xətti, bir cari şöbə."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import CLOSED_STATUSES, ApplicationStatus, SenderFamily

_CTX = "applications"


class Application(UUIDModel, TimeStampedModel):
    """Bir müraciət.

    ``current_unit`` + ``current_scope_unit`` cütü «indi kimdədir» sualının
    cavabıdır: şöbə (rol dəsti) + həmin şöbənin AİDİYYƏTLİ bölməsi
    (dekanlıq üçün fakültə, kafedra üçün kafedra, koordinator üçün ixtisas).
    Mərkəzi şöbələrdə ``current_scope_unit`` NULL olur — bütün təşkilat.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="applications",
    )
    number = models.CharField(max_length=20, db_index=True)
    kind = models.ForeignKey(
        "applications.ApplicationKind",
        on_delete=models.PROTECT,
        related_name="applications",
    )
    subject = models.CharField(max_length=255)
    body = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="applications_created",
    )
    sender_family = models.CharField(max_length=16, choices=SenderFamily.choices)
    sender_scope_unit = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applications_sent",
        help_text="Göndərənin öz bölməsi (tələbə: qrup, müəllim: kafedra).",
    )

    status = models.CharField(
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.SUBMITTED,
        db_index=True,
    )
    current_unit = models.ForeignKey(
        "applications.ApplicationUnit",
        on_delete=models.PROTECT,
        related_name="current_applications",
    )
    current_scope_unit = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applications_at_unit",
        help_text="Cari şöbənin aidiyyət bölməsi; mərkəzi şöbədə NULL.",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applications_assigned",
    )

    sla_due_on = models.DateField(null=True, blank=True, db_index=True)
    submitted_at = models.DateTimeField(default=timezone.now, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = models.Manager()

    class Meta:
        ordering = ["-last_activity_at", "-submitted_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="uniq_application_number"),
        ]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "created_by", "-submitted_at"]),
            models.Index(fields=["organization", "current_unit", "status"]),
            models.Index(fields=["organization", "current_scope_unit"]),
        ]
        verbose_name = pgettext_lazy(_CTX, "müraciət")
        verbose_name_plural = pgettext_lazy(_CTX, "müraciətlər")

    def __str__(self):
        return f"{self.number} · {self.subject[:40]}"

    # ── Törəmə xassələr ────────────────────────────────────────────────────
    @property
    def is_open(self) -> bool:
        return self.status not in CLOSED_STATUSES

    @property
    def is_overdue(self) -> bool:
        """Açıq VƏ cavab müddəti keçib (iş günü ilə hesablanmış ``sla_due_on``)."""
        if not self.is_open or self.sla_due_on is None:
            return False
        return timezone.localdate() > self.sla_due_on

    @property
    def status_label(self) -> str:
        return str(ApplicationStatus(self.status).label)
