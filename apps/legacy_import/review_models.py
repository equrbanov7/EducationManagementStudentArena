"""Append-only canonical mapping version history for reviewed remaps."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from core.models import TimeStampedModel, UUIDModel

from .models import (
    MODEL_LABEL_PATTERN,
    OPAQUE_KEY_PATTERN,
    SHA256_PATTERN,
    TOKEN_PATTERN,
    LegacyEntityMap,
    _NonDeletableLedgerModel,
    model_label_validator,
    opaque_key_validator,
    sha256_validator,
    token_validator,
)


class LegacyEntityMapVersion(UUIDModel, TimeStampedModel, _NonDeletableLedgerModel):
    """Canonical mapping-in immutable initial/remap snapshot-ı.

    `LegacyEntityMap` stable source identity-ni və ilk mapping-i saxlayır.
    Cari canonical nəticə ən böyük `version_number` olan bu append-only
    tarixçədən həll edilir; əvvəlki version və observation dəyişdirilmir.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="legacy_entity_map_versions",
    )
    entity_map = models.ForeignKey(
        LegacyEntityMap,
        on_delete=models.PROTECT,
        related_name="versions",
    )
    version_number = models.PositiveIntegerField()
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="replacement_versions",
    )
    recorded_run = models.ForeignKey(
        "legacy_import.LegacyMigrationRun",
        on_delete=models.PROTECT,
        related_name="recorded_map_versions",
    )
    source_row_hash = models.CharField(max_length=64, validators=[sha256_validator])
    transform_version = models.CharField(max_length=64, validators=[token_validator])
    target_model_label = models.CharField(
        max_length=100,
        validators=[model_label_validator],
        blank=True,
        default="",
    )
    target_pk = models.CharField(max_length=255, validators=[opaque_key_validator], blank=True, default="")
    state = models.CharField(max_length=16, choices=LegacyEntityMap.State.choices)
    reconciliation_status = models.CharField(
        max_length=16,
        choices=LegacyEntityMap.ReconciliationStatus.choices,
        default=LegacyEntityMap.ReconciliationStatus.PENDING,
    )
    approved_issue = models.OneToOneField(
        "legacy_import.LegacyMigrationIssue",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_map_version",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviewed_legacy_entity_map_versions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_reason_code = models.CharField(max_length=64, validators=[token_validator], blank=True, default="")
    review_evidence_digest = models.CharField(
        max_length=64,
        validators=[sha256_validator],
        blank=True,
        default="",
    )
    applied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="applied_legacy_entity_remaps",
    )

    class Meta:
        ordering = ["entity_map_id", "version_number"]
        indexes = [
            models.Index(fields=["organization", "recorded_run"], name="legacy_ver_org_run"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["entity_map", "version_number"], name="legacy_ver_map_no_uniq"),
            models.CheckConstraint(condition=Q(version_number__gte=1), name="legacy_ver_number_positive"),
            models.CheckConstraint(
                condition=Q(source_row_hash__regex=SHA256_PATTERN),
                name="legacy_ver_row_sha_hex",
            ),
            models.CheckConstraint(
                condition=Q(transform_version__regex=TOKEN_PATTERN),
                name="legacy_ver_transform_token",
            ),
            models.CheckConstraint(
                condition=Q(target_model_label="") | Q(target_model_label__regex=MODEL_LABEL_PATTERN),
                name="legacy_ver_model_label",
            ),
            models.CheckConstraint(
                condition=Q(target_pk="") | Q(target_pk__regex=OPAQUE_KEY_PATTERN),
                name="legacy_ver_target_pk_token",
            ),
            models.CheckConstraint(
                condition=(
                    Q(state="migrated") & ~Q(target_model_label="") & ~Q(target_pk="")
                    | Q(state__in=["skipped", "quarantined"], target_model_label="", target_pk="")
                ),
                name="legacy_ver_target_by_state",
            ),
            models.CheckConstraint(
                condition=Q(state__in=["migrated", "skipped", "quarantined"]),
                name="legacy_ver_state_choice",
            ),
            models.CheckConstraint(
                condition=Q(reconciliation_status__in=["pending", "verified", "mismatch", "not_applicable"]),
                name="legacy_ver_recon_choice",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        version_number=1,
                        supersedes__isnull=True,
                        approved_issue__isnull=True,
                        reviewed_by__isnull=True,
                        reviewed_at__isnull=True,
                        review_reason_code="",
                        review_evidence_digest="",
                        applied_by__isnull=True,
                    )
                    | Q(
                        version_number__gt=1,
                        supersedes__isnull=False,
                        approved_issue__isnull=False,
                        reviewed_by__isnull=False,
                        reviewed_at__isnull=False,
                        review_reason_code__regex=TOKEN_PATTERN,
                        review_evidence_digest__regex=SHA256_PATTERN,
                        applied_by__isnull=False,
                    )
                ),
                name="legacy_ver_review_shape",
            ),
        ]

    @property
    def snapshot(self):
        return {
            "source_row_hash": self.source_row_hash,
            "transform_version": self.transform_version,
            "target_model_label": self.target_model_label,
            "target_pk": self.target_pk,
            "state": self.state,
            "reconciliation_status": self.reconciliation_status,
        }

    def clean(self):
        super().clean()
        errors = {}
        if not self.entity_map_id or not self.recorded_run_id:
            return
        map_row = (
            LegacyEntityMap.objects.filter(pk=self.entity_map_id)
            .values(
                "organization_id",
                "source_system",
                "created_run_id",
                "source_row_hash",
                "transform_version",
                "target_model_label",
                "target_pk",
                "state",
                "reconciliation_status",
            )
            .first()
        )
        run_model = self._meta.get_field("recorded_run").remote_field.model
        run_row = (
            run_model.objects.filter(pk=self.recorded_run_id)
            .values(
                "organization_id",
                "source_system",
                "transform_version",
            )
            .first()
        )
        if map_row is None or run_row is None:
            return
        if self.organization_id != map_row["organization_id"]:
            errors["organization"] = "Version və entity map eyni təşkilata aid olmalıdır."
        if run_row["organization_id"] != self.organization_id or run_row["source_system"] != map_row["source_system"]:
            errors["recorded_run"] = "Version run-ı canonical source scope ilə uyğun deyil."
        if run_row["transform_version"] != self.transform_version:
            errors["transform_version"] = "Version transform-u recorded run ilə uyğun deyil."
        if self.version_number == 1:
            base_snapshot = {key: map_row[key] for key in self.snapshot}
            if self.recorded_run_id != map_row["created_run_id"] or self.snapshot != base_snapshot:
                errors["version_number"] = "İlkin version immutable entity map snapshot-ı ilə eyni olmalıdır."
        else:
            predecessor = type(self).objects.filter(pk=self.supersedes_id).first()
            if (
                predecessor is None
                or predecessor.entity_map_id != self.entity_map_id
                or predecessor.version_number + 1 != self.version_number
            ):
                errors["supersedes"] = "Remap version birbaşa əvvəlki version-u əvəz etməlidir."
            elif predecessor.snapshot == self.snapshot:
                errors["version_number"] = "Remap canonical snapshot-ı dəyişməlidir."
            issue = self.approved_issue
            if (
                issue is None
                or issue.entity_map_id != self.entity_map_id
                or issue.organization_id != self.organization_id
                or issue.run_id != self.recorded_run_id
                or issue.rule_code != "legacy_entity_identity_conflict"
                or issue.review_status != issue.ReviewStatus.RESOLVED
                or issue.reviewed_by_id != self.reviewed_by_id
                or issue.reviewed_at != self.reviewed_at
                or issue.review_reason_code != self.review_reason_code
                or issue.review_evidence_digest != self.review_evidence_digest
            ):
                errors["approved_issue"] = "Remap matching resolved review evidence tələb edir."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.entity_map_id}/v{self.version_number}: {self.state}"


class LegacyImportBatch(UUIDModel, TimeStampedModel, _NonDeletableLedgerModel):
    """Miqyaslana bilən, append-only source-row uçot batch-i.

    Hər non-empty source cədvəli monoton integer PK intervalları ilə oxunur.
    Batch digest-ləri raw dəyər saxlamadan bütün sətrlərin təsnifatını və
    zəncir ardıcıllığını sonradan təkrar hesablamağa imkan verir. Fərdi mapping
    və review tələb edən sətrlər mövcud entity-map/issue ledger-ində qalır.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="legacy_import_batches",
    )
    run = models.ForeignKey(
        "legacy_import.LegacyMigrationRun",
        on_delete=models.PROTECT,
        related_name="batches",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_legacy_import_batches",
    )
    source_table = models.CharField(max_length=64, validators=[token_validator])
    entity_type = models.CharField(max_length=64, validators=[token_validator])
    sequence = models.PositiveIntegerField()
    first_legacy_pk = models.PositiveBigIntegerField()
    last_legacy_pk = models.PositiveBigIntegerField()
    source_row_count = models.PositiveIntegerField()
    migrated_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    quarantined_count = models.PositiveIntegerField(default=0)
    contract_fingerprint = models.CharField(max_length=64, validators=[sha256_validator])
    source_digest = models.CharField(max_length=64, validators=[sha256_validator])
    classification_digest = models.CharField(max_length=64, validators=[sha256_validator])
    target_digest = models.CharField(max_length=64, validators=[sha256_validator])
    previous_chain_digest = models.CharField(
        max_length=64,
        validators=[sha256_validator],
        blank=True,
        default="",
    )
    chain_digest = models.CharField(max_length=64, validators=[sha256_validator])

    class Meta:
        ordering = ["run_id", "source_table", "entity_type", "sequence"]
        indexes = [
            models.Index(
                fields=["organization", "run", "source_table"],
                name="legacy_batch_org_run_table",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "source_table", "sequence"],
                name="legacy_batch_run_table_seq_uniq",
            ),
            models.CheckConstraint(condition=Q(sequence__gte=1), name="legacy_batch_sequence_positive"),
            models.CheckConstraint(
                condition=Q(source_row_count__gte=1),
                name="legacy_batch_rows_positive",
            ),
            models.CheckConstraint(
                condition=Q(first_legacy_pk__lte=models.F("last_legacy_pk")),
                name="legacy_batch_pk_range_valid",
            ),
            models.CheckConstraint(
                condition=Q(first_legacy_pk__gte=1),
                name="legacy_batch_first_pk_positive",
            ),
            models.CheckConstraint(
                condition=Q(last_legacy_pk__gte=1),
                name="legacy_batch_last_pk_positive",
            ),
            models.CheckConstraint(
                condition=Q(source_row_count__lte=(models.F("last_legacy_pk") - models.F("first_legacy_pk") + 1)),
                name="legacy_batch_rows_within_pk_range",
            ),
            models.CheckConstraint(
                condition=Q(
                    source_row_count=(
                        models.F("migrated_count") + models.F("skipped_count") + models.F("quarantined_count")
                    )
                ),
                name="legacy_batch_counts_total",
            ),
            models.CheckConstraint(
                condition=(
                    Q(sequence=1, previous_chain_digest="")
                    | Q(sequence__gt=1, previous_chain_digest__regex=SHA256_PATTERN)
                ),
                name="legacy_batch_previous_shape",
            ),
            models.CheckConstraint(
                condition=Q(contract_fingerprint__regex=SHA256_PATTERN),
                name="legacy_batch_contract_sha_hex",
            ),
            models.CheckConstraint(
                condition=Q(source_digest__regex=SHA256_PATTERN),
                name="legacy_batch_source_sha_hex",
            ),
            models.CheckConstraint(
                condition=Q(classification_digest__regex=SHA256_PATTERN),
                name="legacy_batch_class_sha_hex",
            ),
            models.CheckConstraint(
                condition=Q(target_digest__regex=SHA256_PATTERN),
                name="legacy_batch_target_sha_hex",
            ),
            models.CheckConstraint(
                condition=Q(chain_digest__regex=SHA256_PATTERN),
                name="legacy_batch_chain_sha_hex",
            ),
        ]

    def clean(self):
        super().clean()
        if not self.run_id:
            return
        run_model = self._meta.get_field("run").remote_field.model
        run_scope = (
            run_model.objects.filter(pk=self.run_id)
            .values_list(
                "organization_id",
                "status",
            )
            .first()
        )
        errors = {}
        if run_scope is None:
            return
        if run_scope[0] != self.organization_id:
            errors["run"] = "Batch və run eyni təşkilata aid olmalıdır."
        if run_scope[1] != run_model.Status.RUNNING:
            errors["run"] = "Batch yalnız aktiv migration run-a yazıla bilər."
        if self.sequence > 1:
            predecessor = (
                type(self)
                .objects.filter(
                    run_id=self.run_id,
                    source_table=self.source_table,
                    sequence=self.sequence - 1,
                )
                .values_list(
                    "last_legacy_pk",
                    "chain_digest",
                    "entity_type",
                    "contract_fingerprint",
                )
                .first()
            )
            if predecessor is None:
                errors["sequence"] = "Batch zəncirində əvvəlki sıra çatışmır."
            elif (
                self.first_legacy_pk <= predecessor[0]
                or self.previous_chain_digest != predecessor[1]
                or self.entity_type != predecessor[2]
                or self.contract_fingerprint != predecessor[3]
            ):
                errors["previous_chain_digest"] = "Batch PK və digest zənciri uyğun deyil."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.source_table}/{self.entity_type}#{self.sequence}"
