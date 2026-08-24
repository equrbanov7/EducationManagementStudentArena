"""Durable evidence models for the imported-account access lifecycle."""

import uuid

from django.db import models


class AccountActivationEvidence(models.Model):
    """Append-only proof that one staged identity was explicitly unlocked."""

    class Reason(models.TextChoices):
        INSTITUTION_REGISTRY_MATCH = "institution_registry_match", "Institution registry match"
        MANUAL_REGISTRY_VERIFICATION = "manual_registry_verification", "Manual registry verification"
        SIGNED_AUTHORITATIVE_EXPORT = "signed_authoritative_export", "Signed authoritative export"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="account_activation_evidence",
    )
    user_ref = models.CharField(max_length=64, editable=False)
    role_ref = models.CharField(max_length=64, editable=False)
    actor_ref = models.CharField(max_length=64, editable=False)
    evidence_digest = models.CharField(max_length=64, editable=False)
    reason_code = models.CharField(max_length=64, choices=Reason.choices, editable=False)
    transaction_id = models.PositiveBigIntegerField(editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    # The SECURITY DEFINER activation function creates the evidence first and
    # consumes it only after every identity transition succeeds.  A committed
    # row is therefore always consumed; NULL exists only inside that one DB
    # transaction (and makes partial/manual activation impossible to disguise).
    consumed_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user_ref"],
                name="accounts_activation_evidence_user_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=["organization", "created_at"],
                name="accounts_act_org_created_idx",
            )
        ]

    def __str__(self):
        return f"activation-evidence:{self.pk}"


__all__ = ["AccountActivationEvidence"]
