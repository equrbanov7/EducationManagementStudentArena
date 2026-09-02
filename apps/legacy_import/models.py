"""Legacy import üçün xam payload-sız, PII-minimised idarəetmə modelləri.

Bu modul mənbə sətrinin özünü, DSN-i, credential-ı və ya sərbəst xəta mətnini
saxlamır. Opaque legacy ID və stabil digest-lər linkable pseudonymous data-dır.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.deletion import ProtectedError

from core.models import TimeStampedModel, UUIDModel

TOKEN_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
OPAQUE_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$"
MODEL_LABEL_PATTERN = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"
_RUN_MODE_CHECK = Q(mode__in=["profile", "rehearsal", "cutover"])
_RUN_ACCOUNTING_CHECK = Q(accounting_mode__in=["row", "batch"])

token_validator = RegexValidator(
    regex=TOKEN_PATTERN,
    message="Yalnız kiçik hərf, rəqəm, nöqtə, alt xətt və defis istifadə edilə bilər.",
)
sha256_validator = RegexValidator(
    regex=SHA256_PATTERN,
    message="Dəyər kiçik hərfli 64 simvolluq SHA-256 hex digest olmalıdır.",
)
opaque_key_validator = RegexValidator(
    regex=OPAQUE_KEY_PATTERN,
    message="Açar yalnız opaque identifikator simvollarından ibarət olmalıdır.",
)
model_label_validator = RegexValidator(
    regex=MODEL_LABEL_PATTERN,
    message="Target model etiketi app_label.model_name formatında olmalıdır.",
)


class _NoDeleteQuerySet(models.QuerySet):
    def delete(self):
        raise ProtectedError("Legacy import ledger sətirləri silinə bilməz.", self)


class _NoDeleteManager(models.Manager.from_queryset(_NoDeleteQuerySet)):
    pass


class _NonDeletableLedgerModel(models.Model):
    objects = _NoDeleteManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        raise ProtectedError("Legacy import ledger sətirləri silinə bilməz.", [self])


class LegacyMigrationRun(UUIDModel, TimeStampedModel, _NonDeletableLedgerModel):
    """Bir immutable source snapshot üzərində aparılan import icrası."""

    class Mode(models.TextChoices):
        PROFILE = "profile", "Profiling"
        REHEARSAL = "rehearsal", "Rehearsal"
        CUTOVER = "cutover", "Cutover"

    class Status(models.TextChoices):
        PENDING = "pending", "Gözləyir"
        RUNNING = "running", "İcra olunur"
        SUCCEEDED = "succeeded", "Uğurlu"
        FAILED = "failed", "Uğursuz"
        CANCELLED = "cancelled", "Dayandırılıb"

    class Origin(models.TextChoices):
        MANUAL = "manual", "Manual"
        COMMAND = "command", "Management command"

    class AccountingMode(models.TextChoices):
        ROW = "row", "Row ledger"
        BATCH = "batch", "Batch ledger"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="legacy_migration_runs",
    )
    source_system = models.CharField(max_length=64, validators=[token_validator])
    snapshot_sha256 = models.CharField(max_length=64, validators=[sha256_validator])
    snapshot_size_bytes = models.PositiveBigIntegerField()
    source_row_count = models.PositiveBigIntegerField(default=0)
    schema_version = models.CharField(max_length=64, validators=[token_validator])
    transform_version = models.CharField(max_length=64, validators=[token_validator])
    mode = models.CharField(max_length=16, choices=Mode.choices)
    accounting_mode = models.CharField(max_length=8, choices=AccountingMode.choices, default=AccountingMode.ROW)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    origin = models.CharField(max_length=16, choices=Origin.choices, default=Origin.MANUAL)
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_migration_runs",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    migrated_count = models.PositiveBigIntegerField(default=0)
    skipped_count = models.PositiveBigIntegerField(default=0)
    quarantined_count = models.PositiveBigIntegerField(default=0)
    failure_code = models.CharField(max_length=64, validators=[token_validator], blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "source_system", "status"], name="legacy_run_org_src_status"),
            models.Index(fields=["organization", "snapshot_sha256"], name="legacy_run_org_snapshot"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(snapshot_sha256__regex=SHA256_PATTERN),
                name="legacy_run_snapshot_sha_hex",
            ),
            models.CheckConstraint(
                condition=Q(source_system__regex=TOKEN_PATTERN),
                name="legacy_run_source_token",
            ),
            models.CheckConstraint(
                condition=Q(schema_version__regex=TOKEN_PATTERN),
                name="legacy_run_schema_token",
            ),
            models.CheckConstraint(
                condition=Q(transform_version__regex=TOKEN_PATTERN),
                name="legacy_run_transform_token",
            ),
            models.CheckConstraint(
                condition=Q(failure_code="") | Q(failure_code__regex=TOKEN_PATTERN),
                name="legacy_run_failure_token",
            ),
            models.CheckConstraint(
                condition=Q(migrated_count__lte=(F("source_row_count") - F("skipped_count") - F("quarantined_count"))),
                name="legacy_run_counts_within_total",
            ),
            models.CheckConstraint(condition=_RUN_MODE_CHECK, name="legacy_run_mode_choice"),
            models.CheckConstraint(condition=_RUN_ACCOUNTING_CHECK, name="legacy_run_accounting_choice"),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "running", "succeeded", "failed", "cancelled"]),
                name="legacy_run_status_choice",
            ),
            models.CheckConstraint(
                condition=Q(origin__in=["manual", "command"]),
                name="legacy_run_origin_choice",
            ),
        ]

    def __str__(self):
        return f"{self.source_system}: {self.mode}/{self.status}"


class LegacyEntityMap(UUIDModel, TimeStampedModel, _NonDeletableLedgerModel):
    """Legacy source identity üçün canonical, dəyişdirilməz target mapping-i."""

    class State(models.TextChoices):
        MIGRATED = "migrated", "Miqrasiya edilib"
        SKIPPED = "skipped", "Buraxılıb"
        QUARANTINED = "quarantined", "Quarantine"

    class ReconciliationStatus(models.TextChoices):
        PENDING = "pending", "Gözləyir"
        VERIFIED = "verified", "Təsdiqlənib"
        MISMATCH = "mismatch", "Uyğunsuzluq"
        NOT_APPLICABLE = "not_applicable", "Tətbiq edilmir"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="legacy_entity_maps",
    )
    source_system = models.CharField(max_length=64, validators=[token_validator])
    entity_type = models.CharField(max_length=64, validators=[token_validator])
    legacy_pk = models.CharField(max_length=255, validators=[opaque_key_validator])
    source_row_hash = models.CharField(max_length=64, validators=[sha256_validator])
    transform_version = models.CharField(max_length=64, validators=[token_validator])
    target_model_label = models.CharField(
        max_length=100,
        validators=[model_label_validator],
        blank=True,
        default="",
    )
    target_pk = models.CharField(max_length=255, validators=[opaque_key_validator], blank=True, default="")
    created_run = models.ForeignKey(
        LegacyMigrationRun,
        on_delete=models.PROTECT,
        related_name="created_entity_maps",
        help_text="Canonical mapping-in ilk yaradıldığı run; sonrakı run-lar observation kimi saxlanır.",
    )
    state = models.CharField(max_length=16, choices=State.choices)
    reconciliation_status = models.CharField(
        max_length=16,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.PENDING,
    )

    class Meta:
        ordering = ["source_system", "entity_type", "legacy_pk"]
        indexes = [
            models.Index(fields=["organization", "created_run", "state"], name="legacy_map_org_created_state"),
            models.Index(fields=["target_model_label", "target_pk"], name="legacy_map_target"),
            # «Bu açılış köçürülüb?» sorğusu (``exam_eligibility._migrated_offering_ids``)
            # ``target_model_label`` SÜZMÜR — yəni yuxarıdakı kompozit indeksin
            # aparıcı sütununa oturmur və Postgres 5 000+ səhifə oxuyurdu
            # (tək sətir üçün 20-97 ms; 2026-09-02 EXPLAIN ANALYZE).
            models.Index(fields=["entity_type", "state", "target_pk"], name="legacy_map_lookup"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "source_system", "entity_type", "legacy_pk"],
                name="legacy_map_source_key_uniq",
            ),
            models.CheckConstraint(
                condition=Q(source_system__regex=TOKEN_PATTERN),
                name="legacy_map_source_token",
            ),
            models.CheckConstraint(
                condition=Q(entity_type__regex=TOKEN_PATTERN),
                name="legacy_map_entity_token",
            ),
            models.CheckConstraint(
                condition=Q(source_row_hash__regex=SHA256_PATTERN),
                name="legacy_map_row_sha_hex",
            ),
            models.CheckConstraint(
                condition=Q(transform_version__regex=TOKEN_PATTERN),
                name="legacy_map_transform_token",
            ),
            models.CheckConstraint(
                condition=Q(legacy_pk__regex=OPAQUE_KEY_PATTERN),
                name="legacy_map_pk_token",
            ),
            models.CheckConstraint(
                condition=Q(target_model_label="") | Q(target_model_label__regex=MODEL_LABEL_PATTERN),
                name="legacy_map_model_label",
            ),
            models.CheckConstraint(
                condition=Q(target_pk="") | Q(target_pk__regex=OPAQUE_KEY_PATTERN),
                name="legacy_map_target_pk_token",
            ),
            models.CheckConstraint(
                condition=(
                    Q(state="migrated") & ~Q(target_model_label="") & ~Q(target_pk="")
                    | Q(state__in=["skipped", "quarantined"], target_model_label="", target_pk="")
                ),
                name="legacy_map_target_by_state",
            ),
            models.CheckConstraint(
                condition=Q(state__in=["migrated", "skipped", "quarantined"]),
                name="legacy_map_state_choice",
            ),
            models.CheckConstraint(
                condition=Q(reconciliation_status__in=["pending", "verified", "mismatch", "not_applicable"]),
                name="legacy_map_recon_choice",
            ),
        ]

    def clean(self):
        super().clean()
        if not self.created_run_id:
            return
        run_scope = (
            LegacyMigrationRun.objects.filter(pk=self.created_run_id)
            .values_list("organization_id", "source_system", "transform_version")
            .first()
        )
        if run_scope is None:
            return
        run_organization_id, run_source_system, run_transform_version = run_scope
        errors = {}
        if self.organization_id and run_organization_id != self.organization_id:
            errors["created_run"] = "Run və entity map eyni təşkilata aid olmalıdır."
        if self.source_system and run_source_system != self.source_system:
            errors["source_system"] = "Run və entity map eyni source system-ə aid olmalıdır."
        if self.transform_version and run_transform_version != self.transform_version:
            errors["transform_version"] = "Run və entity map eyni transform versiyasına aid olmalıdır."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.source_system}/{self.entity_type}: {self.state}"


class LegacyEntityObservation(UUIDModel, TimeStampedModel, _NonDeletableLedgerModel):
    """Bir run-da canonical entity mapping-i üçün immutable nəticə snapshot-ı."""

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="legacy_entity_observations",
    )
    run = models.ForeignKey(
        LegacyMigrationRun,
        on_delete=models.PROTECT,
        related_name="entity_observations",
    )
    entity_map = models.ForeignKey(
        LegacyEntityMap,
        on_delete=models.PROTECT,
        related_name="observations",
    )
    map_version = models.ForeignKey(
        "legacy_import.LegacyEntityMapVersion",
        on_delete=models.PROTECT,
        related_name="observations",
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

    class Meta:
        ordering = ["run_id", "entity_map_id"]
        indexes = [
            models.Index(fields=["organization", "run", "state"], name="legacy_obs_org_run_state"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["run", "entity_map"], name="legacy_obs_run_map_uniq"),
            models.CheckConstraint(
                condition=Q(source_row_hash__regex=SHA256_PATTERN),
                name="legacy_obs_row_sha_hex",
            ),
            models.CheckConstraint(
                condition=Q(transform_version__regex=TOKEN_PATTERN),
                name="legacy_obs_transform_token",
            ),
            models.CheckConstraint(
                condition=Q(target_model_label="") | Q(target_model_label__regex=MODEL_LABEL_PATTERN),
                name="legacy_obs_model_label",
            ),
            models.CheckConstraint(
                condition=Q(target_pk="") | Q(target_pk__regex=OPAQUE_KEY_PATTERN),
                name="legacy_obs_target_pk_token",
            ),
            models.CheckConstraint(
                condition=(
                    Q(state="migrated") & ~Q(target_model_label="") & ~Q(target_pk="")
                    | Q(state__in=["skipped", "quarantined"], target_model_label="", target_pk="")
                ),
                name="legacy_obs_target_by_state",
            ),
            models.CheckConstraint(
                condition=Q(state__in=["migrated", "skipped", "quarantined"]),
                name="legacy_obs_state_choice",
            ),
            models.CheckConstraint(
                condition=Q(reconciliation_status__in=["pending", "verified", "mismatch", "not_applicable"]),
                name="legacy_obs_recon_choice",
            ),
        ]

    def clean(self):
        super().clean()
        if not self.run_id or not self.entity_map_id:
            return
        run_scope = (
            LegacyMigrationRun.objects.filter(pk=self.run_id)
            .values_list("organization_id", "source_system", "transform_version")
            .first()
        )
        version_scope = (
            LegacyEntityMapVersion.objects.filter(pk=self.map_version_id)
            .values_list(
                "organization_id",
                "entity_map_id",
                "entity_map__source_system",
                "source_row_hash",
                "transform_version",
                "target_model_label",
                "target_pk",
                "state",
                "reconciliation_status",
            )
            .first()
        )
        if run_scope is None or version_scope is None:
            return
        expected = (
            self.organization_id,
            self.entity_map_id,
            run_scope[1],
            self.source_row_hash,
            self.transform_version,
            self.target_model_label,
            self.target_pk,
            self.state,
            self.reconciliation_status,
        )
        errors = {}
        if run_scope[0] != self.organization_id or run_scope[2] != self.transform_version:
            errors["run"] = "Observation run scope ilə uyğun deyil."
        if version_scope != expected:
            errors["map_version"] = "Observation canonical mapping versiyası ilə eyni deyil."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.run_id}/{self.entity_map_id}: {self.state}"


class LegacyMigrationIssue(UUIDModel, TimeStampedModel, _NonDeletableLedgerModel):
    """Raw payload-sız problem; metadata son tamamlanmış review qərarıdır."""

    class Severity(models.TextChoices):
        INFO = "info", "Məlumat"
        WARNING = "warning", "Xəbərdarlıq"
        ERROR = "error", "Xəta"
        CRITICAL = "critical", "Kritik"

    class ReviewStatus(models.TextChoices):
        OPEN = "open", "Açıq"
        ACKNOWLEDGED = "acknowledged", "Qəbul edilib"
        RESOLVED = "resolved", "Həll edilib"
        WAIVED = "waived", "İstisna təsdiqlənib"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="legacy_migration_issues",
    )
    run = models.ForeignKey(
        LegacyMigrationRun,
        on_delete=models.PROTECT,
        related_name="issues",
    )
    entity_map = models.ForeignKey(
        LegacyEntityMap,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="issues",
    )
    source_table = models.CharField(max_length=64, validators=[token_validator])
    entity_type = models.CharField(max_length=64, validators=[token_validator])
    legacy_pk = models.CharField(max_length=255, validators=[opaque_key_validator])
    rule_code = models.CharField(max_length=64, validators=[token_validator])
    severity = models.CharField(max_length=16, choices=Severity.choices)
    review_status = models.CharField(max_length=16, choices=ReviewStatus.choices, default=ReviewStatus.OPEN)
    payload_digest = models.CharField(max_length=64, validators=[sha256_validator])
    # OPEN + metadata severity escalation-dan əvvəlki son review qərarı deməkdir.
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviewed_legacy_migration_issues",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_reason_code = models.CharField(max_length=64, validators=[token_validator], blank=True, default="")
    review_evidence_digest = models.CharField(
        max_length=64,
        validators=[sha256_validator],
        blank=True,
        default="",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "review_status", "severity"], name="legacy_issue_org_review"),
            models.Index(fields=["run", "entity_type"], name="legacy_issue_run_entity"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "source_table", "legacy_pk", "rule_code"],
                name="legacy_issue_row_rule_uniq",
            ),
            models.CheckConstraint(
                condition=Q(source_table__regex=TOKEN_PATTERN),
                name="legacy_issue_table_token",
            ),
            models.CheckConstraint(
                condition=Q(entity_type__regex=TOKEN_PATTERN),
                name="legacy_issue_entity_token",
            ),
            models.CheckConstraint(
                condition=Q(rule_code__regex=TOKEN_PATTERN),
                name="legacy_issue_rule_token",
            ),
            models.CheckConstraint(
                condition=Q(payload_digest__regex=SHA256_PATTERN),
                name="legacy_issue_digest_hex",
            ),
            models.CheckConstraint(
                condition=Q(legacy_pk__regex=OPAQUE_KEY_PATTERN),
                name="legacy_issue_pk_token",
            ),
            models.CheckConstraint(
                condition=Q(severity__in=["info", "warning", "error", "critical"]),
                name="legacy_issue_severity_choice",
            ),
            models.CheckConstraint(
                condition=Q(review_status__in=["open", "acknowledged", "resolved", "waived"]),
                name="legacy_issue_review_choice",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        reviewed_by__isnull=True,
                        reviewed_at__isnull=True,
                        review_reason_code="",
                        review_evidence_digest="",
                    )
                    | Q(
                        reviewed_by__isnull=False,
                        reviewed_at__isnull=False,
                        review_reason_code__regex=TOKEN_PATTERN,
                        review_evidence_digest__regex=SHA256_PATTERN,
                    )
                ),
                name="legacy_issue_review_evidence_shape",
            ),
            models.CheckConstraint(
                condition=Q(review_status="open")
                | Q(
                    reviewed_by__isnull=False,
                    reviewed_at__isnull=False,
                    review_reason_code__regex=TOKEN_PATTERN,
                    review_evidence_digest__regex=SHA256_PATTERN,
                ),
                name="legacy_issue_decision_has_review",
            ),
        ]

    def clean(self):
        super().clean()
        if not self.run_id:
            return
        errors = {}
        run_scope = (
            LegacyMigrationRun.objects.filter(pk=self.run_id)
            .values_list("organization_id", "source_system", "transform_version")
            .first()
        )
        if run_scope is None:
            return
        run_organization_id, run_source_system, run_transform_version = run_scope
        if self.organization_id and run_organization_id != self.organization_id:
            errors["run"] = "Run və issue eyni təşkilata aid olmalıdır."
        if self.entity_map_id:
            map_scope = (
                LegacyEntityMap.objects.filter(pk=self.entity_map_id)
                .values_list("organization_id", "source_system", "entity_type", "legacy_pk")
                .first()
            )
            if map_scope is None:
                if errors:
                    raise ValidationError(errors)
                return
            map_organization_id, map_source_system, map_entity_type, map_legacy_pk = map_scope
            if self.organization_id and map_organization_id != self.organization_id:
                errors["entity_map"] = "Entity map və issue eyni təşkilata aid olmalıdır."
            elif run_source_system != map_source_system:
                errors["entity_map"] = "Entity map issue run-ının source system-inə aid olmalıdır."
            elif map_entity_type != self.entity_type or map_legacy_pk != self.legacy_pk:
                errors["entity_map"] = "Entity map issue sətrinin identity-si ilə uyğun deyil."
            elif (
                self.rule_code != "legacy_entity_identity_conflict"
                and not LegacyEntityObservation.objects.filter(
                    run_id=self.run_id,
                    entity_map_id=self.entity_map_id,
                    transform_version=run_transform_version,
                ).exists()
            ):
                errors["entity_map"] = "Issue run-ında matching canonical observation tələb olunur."
        evidence_values = (
            self.reviewed_by_id,
            self.reviewed_at,
            self.review_reason_code,
            self.review_evidence_digest,
        )
        has_any_evidence = any(value not in (None, "") for value in evidence_values)
        has_all_evidence = all(value not in (None, "") for value in evidence_values)
        if has_any_evidence and not has_all_evidence:
            errors["review_status"] = "Review actor, vaxt, səbəb və evidence birlikdə tələb olunur."
        if self.review_status != self.ReviewStatus.OPEN and not has_all_evidence:
            errors["review_status"] = "Terminal review qərarı tam review evidence tələb edir."
        if self.created_at and self.reviewed_at and self.reviewed_at < self.created_at:
            errors["reviewed_at"] = "Review vaxtı issue yaradılma vaxtından əvvəl ola bilməz."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.rule_code}: {self.severity}/{self.review_status}"


from .review_models import LegacyEntityMapVersion, LegacyImportBatch  # noqa: E402,F401
