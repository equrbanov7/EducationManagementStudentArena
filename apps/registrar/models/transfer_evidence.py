"""Append-only evidence for sanctioned student group transfers."""

from django.core.exceptions import ValidationError
from django.db import models

from core.models import UUIDModel


class GroupTransferEvidence(UUIDModel):
    """Durable record/old/new/actor proof emitted with a group transition."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="group_transfer_evidence",
    )
    record = models.ForeignKey(
        "registrar.StudentAcademicRecord",
        on_delete=models.PROTECT,
        related_name="group_transfer_evidence",
    )
    old_group = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    new_group = models.ForeignKey(
        "organizations.OrgUnit",
        on_delete=models.PROTECT,
        related_name="+",
    )
    period = models.ForeignKey(
        "organizations.AcademicPeriod",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    actor_ref = models.PositiveBigIntegerField()
    transaction_id = models.CharField(max_length=64)
    expected_enrollment_ids = models.JSONField(default=list)
    audit_ref = models.UUIDField(null=True, blank=True)
    is_finalized = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["record", "transaction_id"],
                name="uniq_group_transfer_record_transaction",
            )
        ]
        indexes = [
            models.Index(
                fields=["organization", "record", "-created_at"],
                name="reg_group_evidence_lookup_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Qrup köçürmə sübutu dəyişdirilə bilməz.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Qrup köçürmə sübutu silinə bilməz.")
