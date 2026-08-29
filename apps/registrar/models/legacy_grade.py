"""Köhnə sistemdən gələn qiymətlərin dəyişdirilməz mənbə sübutu.

Kanonik ``FinalGrade``/``ComponentScore`` cari sistemin hesab məntiqinə xidmət
edir. Bu modellər isə fərqli məqsədlidir: MariaDB-də olan xam giriş, imtahan,
təkrar imtahan və yekun dəyərlərini clamp və yenidən hesablamasız saxlayır.
Beləliklə istifadəçi cari hesabla köhnə mənbə faktını qarışdırmır.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import pgettext_lazy

from .corrections import ImmutableCorrectionEvidence

SHA256_RE = r"\A[0-9a-f]{64}\Z"
TOKEN_RE = r"\A[a-z0-9][a-z0-9._-]{0,63}\Z"
sha256_validator = RegexValidator(SHA256_RE, "SHA-256 lowercase hex formatında olmalıdır.")
token_validator = RegexValidator(TOKEN_RE, "Dəyər təhlükəsiz token formatında olmalıdır.")

# Köhnə rəsmi balı yoxlamaq, kağız imtahan balını daxil etmək kimi yalnız həmin
# qərarı vermək səlahiyyəti olan mərkəzi aktora aiddir. Rol adına bağlanmırıq:
# permission-editor ilə verilən RBAC açarı source-of-truth qalır.
LEGACY_GRADE_REVIEW_PERMISSION = "final_score.entry"


class _AppendOnlyQuerySet(models.QuerySet):
    """SQLite daxil ordinary bulk mutasiyanı da fail-closed saxla."""

    def update(self, **kwargs):
        raise ValidationError("Legacy grade evidence is immutable.")

    def delete(self):
        raise ValidationError("Legacy grade evidence cannot be deleted.")


class _AppendOnlyManager(models.Manager.from_queryset(_AppendOnlyQuerySet)):
    pass


class _ReviewQuerySet(_AppendOnlyQuerySet):
    def bulk_create(self, objs, **kwargs):
        # ``bulk_create`` model ``save/full_clean`` yolunu keçdiyi üçün reviewer
        # icazəsi və ad snapshot-u yoxlanmadan qərar yaza bilərdi.
        raise ValidationError("Legacy grade reviews must be individually authorized.")


class _ReviewManager(models.Manager.from_queryset(_ReviewQuerySet)):
    pass


class LegacyGradeEvidenceKind(models.TextChoices):
    SUMMARY = "summary", pgettext_lazy("registrar.legacy_grade_kind", "Legacy summary")
    EXAM = "exam", pgettext_lazy("registrar.legacy_grade_kind", "Legacy exam")
    RESIT = "resit", pgettext_lazy("registrar.legacy_grade_kind", "Legacy resit")
    EXAM_ENTRY_EXIT = (
        "exam_entry_exit",
        pgettext_lazy("registrar.legacy_grade_kind", "Legacy exam entry/exit attempt"),
    )
    OTHER = "other", pgettext_lazy("registrar.legacy_grade_kind", "Other legacy grade code")


class LegacyGradeMappingStatus(models.TextChoices):
    LINKED = "linked", pgettext_lazy("registrar.legacy_grade_mapping", "Linked")
    GROUP_MISMATCH = "group_mismatch", pgettext_lazy("registrar.legacy_grade_mapping", "Historical group mismatch")
    DISCARDED_SOURCE = "discarded_source", pgettext_lazy("registrar.legacy_grade_mapping", "Discarded legacy journal")
    UNRESOLVED = "unresolved", pgettext_lazy("registrar.legacy_grade_mapping", "Unresolved")
    CONFLICT = "conflict", pgettext_lazy("registrar.legacy_grade_mapping", "Conflicting source rows")


class LegacyGradeReviewDecision(models.TextChoices):
    VERIFIED = "verified", pgettext_lazy("registrar.legacy_grade_review", "Verified")
    DISPUTED = "disputed", pgettext_lazy("registrar.legacy_grade_review", "Disputed")
    CORRECTION_REQUIRED = "correction_required", pgettext_lazy("registrar.legacy_grade_review", "Correction required")


class LegacyGradeArtifactKind(models.TextChoices):
    SCORE_SHEET_EXPORT = (
        "score_sheet_export",
        pgettext_lazy("registrar.legacy_grade_artifact", "Legacy score-sheet export"),
    )


class LegacyGradeFact(ImmutableCorrectionEvidence):
    """Bir köhnə mənbə sətrinin tam, append-only qiymət snapshot-u."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="legacy_grade_facts"
    )
    enrollment = models.ForeignKey(
        "registrar.Enrollment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="legacy_grade_facts",
        help_text="Həll olunubsa cari qeydiyyat; tapılmasa xam fakt yenə saxlanır.",
    )
    source_system = models.CharField(max_length=64, validators=[token_validator])
    source_table = models.CharField(max_length=64, validators=[token_validator])
    source_pk = models.PositiveBigIntegerField()
    source_snapshot_sha256 = models.CharField(max_length=64, validators=[sha256_validator])
    source_row_hash = models.CharField(max_length=64, validators=[sha256_validator])
    materialization_digest = models.CharField(max_length=64, validators=[sha256_validator])
    transform_version = models.CharField(max_length=64, validators=[token_validator])

    evidence_kind = models.CharField(max_length=16, choices=LegacyGradeEvidenceKind.choices)
    score_code = models.CharField(max_length=16, blank=True, default="")
    is_archive = models.BooleanField(default=False)
    mapping_status = models.CharField(max_length=24, choices=LegacyGradeMappingStatus.choices)
    mapping_issue_code = models.CharField(max_length=64, validators=[token_validator], blank=True, default="")

    source_student_ref = models.CharField(max_length=64, blank=True, default="")
    source_journal_ref = models.CharField(max_length=255, blank=True, default="")
    source_lesson_ref = models.CharField(max_length=64, blank=True, default="")
    source_group_ref = models.CharField(max_length=64, blank=True, default="")
    # Hədəf Enrollment UUID-si hər təmiz repetisiyada fərqli yaranır. Bu sahə
    # isə eyni mapping-in mənbə-sabit açarıdır (``journal_uniqid:student_id``):
    # cross-run digest target UUID-dən yox, məhz bundan qurulur.
    source_enrollment_ref = models.CharField(max_length=320, blank=True, default="")

    # Mətn sahələri mənbənin insan-oxunaqlı dəyərini clamp/quantize etmədən
    # qoruyur; Decimal sahələr təhlükəsiz sorğu və çeşidləmə üçündür.
    entry_score_text = models.CharField(max_length=64, blank=True, default="")
    exam_score_text = models.CharField(max_length=64, blank=True, default="")
    resit_score_text = models.CharField(max_length=64, blank=True, default="")
    final_score_text = models.CharField(max_length=64, blank=True, default="")
    raw_score_text = models.CharField(max_length=64, blank=True, default="")
    entry_score = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    exam_score = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    resit_score = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    final_score = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    legacy_kesr = models.IntegerField(null=True, blank=True)
    legacy_level = models.IntegerField(null=True, blank=True)
    legacy_attempt_type = models.IntegerField(null=True, blank=True)
    legacy_recorded_at_text = models.CharField(max_length=64, blank=True, default="")
    legacy_guzest_girish_text = models.CharField(max_length=64, blank=True, default="")
    legacy_guzest_artim_text = models.CharField(max_length=64, blank=True, default="")
    requires_exam_center_review = models.BooleanField(default=True, editable=False)

    objects = _AppendOnlyManager()

    class Meta:
        ordering = ["source_table", "source_pk"]
        verbose_name = pgettext_lazy("registrar.model.legacy_grade_fact.meta", "legacy grade fact")
        verbose_name_plural = pgettext_lazy("registrar.model.legacy_grade_fact.meta", "legacy grade facts")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "source_system", "source_table", "source_pk"],
                name="registrar_legacy_grade_source_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(requires_exam_center_review=True),
                name="registrar_legacy_grade_review_required",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "enrollment"], name="reg_legacy_grade_org_enroll"),
            models.Index(fields=["organization", "mapping_status"], name="reg_legacy_grade_org_map"),
        ]

    def clean(self):
        super().clean()
        linked = self.mapping_status in {
            LegacyGradeMappingStatus.LINKED,
            LegacyGradeMappingStatus.CONFLICT,
        }
        if linked and (not self.enrollment_id or not self.source_enrollment_ref):
            raise ValidationError(
                {"enrollment": "Bağlanmış legacy qiymət faktında mənbə və hədəf qeydiyyat açarı olmalıdır."}
            )
        if not linked and self.enrollment_id:
            raise ValidationError(
                {"enrollment": "Həll olunmamış legacy qiymət faktı kanonik qeydiyyata bağlana bilməz."}
            )
        if self.enrollment_id:
            enrollment_org = (
                type(self)
                .objects.model._meta.apps.get_model("registrar", "Enrollment")
                .objects.filter(pk=self.enrollment_id)
                .values_list("organization_id", flat=True)
                .first()
            )
            if enrollment_org is not None and enrollment_org != self.organization_id:
                raise ValidationError({"enrollment": "Legacy grade fact və qeydiyyat eyni təşkilata aid olmalıdır."})

    def __str__(self):
        return f"legacy-grade<{self.source_table}:{self.source_pk}>"


class LegacyGradeArtifact(ImmutableCorrectionEvidence):
    """Köhnə bal vərəqinin sıxılmış, dəyişdirilməz xam export snapshot-u.

    ``balvereqi_logs.data`` təxminən 1 GB HTML evidence daşıyır. Payload
    ``zlib`` ilə sıxılır, amma mənbənin UTF-8 bayt hash-i və açılmamış ölçüsü
    ayrıca möhürlənir; təqdimat və log qatına xam PII çıxarılmır.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="legacy_grade_artifacts",
    )
    source_system = models.CharField(max_length=64, validators=[token_validator])
    source_table = models.CharField(max_length=64, validators=[token_validator])
    source_pk = models.PositiveBigIntegerField()
    source_snapshot_sha256 = models.CharField(max_length=64, validators=[sha256_validator])
    source_row_hash = models.CharField(max_length=64, validators=[sha256_validator])
    materialization_digest = models.CharField(max_length=64, validators=[sha256_validator])
    transform_version = models.CharField(max_length=64, validators=[token_validator])
    artifact_kind = models.CharField(max_length=32, choices=LegacyGradeArtifactKind.choices)
    source_owner_ref = models.CharField(max_length=64, blank=True, default="")
    source_journal_ref = models.CharField(max_length=255, blank=True, default="")
    source_exported_at_text = models.CharField(max_length=64, blank=True, default="")
    payload_sha256 = models.CharField(max_length=64, validators=[sha256_validator])
    payload_size_bytes = models.PositiveBigIntegerField()
    payload_zlib = models.BinaryField(editable=False)
    requires_exam_center_review = models.BooleanField(default=True, editable=False)

    objects = _AppendOnlyManager()

    class Meta:
        ordering = ["source_table", "source_pk"]
        verbose_name = pgettext_lazy("registrar.model.legacy_grade_artifact.meta", "legacy grade artifact")
        verbose_name_plural = pgettext_lazy(
            "registrar.model.legacy_grade_artifact.meta",
            "legacy grade artifacts",
        )
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "source_system", "source_table", "source_pk"],
                name="registrar_legacy_grade_artifact_source_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(requires_exam_center_review=True),
                name="registrar_legacy_artifact_review_required",
            ),
            models.CheckConstraint(
                condition=models.Q(payload_size_bytes__gt=0),
                name="registrar_legacy_artifact_payload_nonempty",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "source_journal_ref"],
                name="reg_legacy_art_org_journal",
            ),
        ]

    def __str__(self):
        return f"legacy-grade-artifact<{self.source_table}:{self.source_pk}>"


class LegacyGradeReview(ImmutableCorrectionEvidence):
    """İmtahan Mərkəzinin append-only yoxlama qərarı; fakt dəyişməz qalır."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="legacy_grade_reviews"
    )
    fact = models.ForeignKey(LegacyGradeFact, on_delete=models.PROTECT, related_name="reviews")
    decision = models.CharField(max_length=24, choices=LegacyGradeReviewDecision.choices)
    reason_code = models.CharField(max_length=64, validators=[token_validator])
    note = models.TextField(blank=True, default="")
    evidence_digest = models.CharField(max_length=64, validators=[sha256_validator])
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="legacy_grade_reviews"
    )
    reviewed_by_name = models.CharField(max_length=200, editable=False)

    objects = _ReviewManager()

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = pgettext_lazy("registrar.model.legacy_grade_review.meta", "legacy grade review")
        verbose_name_plural = pgettext_lazy("registrar.model.legacy_grade_review.meta", "legacy grade reviews")
        indexes = [
            models.Index(fields=["organization", "fact", "created_at"], name="reg_legacy_review_fact_time"),
        ]

    def clean(self):
        super().clean()
        if self.fact_id:
            fact_org = LegacyGradeFact.objects.filter(pk=self.fact_id).values_list("organization_id", flat=True).first()
            if fact_org is not None and fact_org != self.organization_id:
                raise ValidationError({"fact": "Yoxlama qərarı və qiymət faktı eyni təşkilata aid olmalıdır."})
        if not self._reviewer_has_scope():
            raise ValidationError(
                {"reviewed_by": "Bu istifadəçinin köhnə rəsmi balı yoxlamaq üçün səlahiyyəti yoxdur."}
            )

    def _reviewer_has_scope(self) -> bool:
        """RBAC permission + struktur əhatəsini app-registry yolu ilə yoxla."""

        actor = getattr(self, "reviewed_by", None)
        organization = getattr(self, "organization", None)
        if (
            actor is None
            or organization is None
            or not getattr(actor, "is_active", False)
            or not getattr(organization, "is_active", False)
        ):
            return False
        if getattr(actor, "is_superuser", False) or getattr(actor, "is_superadmin", False):
            return True
        if organization.owner_id == actor.pk:
            return True

        org_unit_model = self._meta.apps.get_model("organizations", "OrgUnit")
        scope = org_unit_model.user_permission_scope(actor, organization, LEGACY_GRADE_REVIEW_PERMISSION)
        if not scope.has_structure_access:
            return False
        if scope.is_org_wide:
            return True

        enrollment_id = LegacyGradeFact.objects.filter(pk=self.fact_id).values_list("enrollment_id", flat=True).first()
        if enrollment_id is None:
            return False
        enrollment_model = self._meta.apps.get_model("registrar", "Enrollment")
        group_id = (
            enrollment_model.objects.filter(pk=enrollment_id, organization=organization)
            .values_list("offering__group_id", flat=True)
            .first()
        )
        if group_id is None:
            return False
        return (
            org_unit_model.objects.filter(organization=organization, pk=group_id)
            .filter(scope.unit_subtree_q())
            .exists()
        )

    def save(self, *args, **kwargs):
        if self._state.adding:
            actor = getattr(self, "reviewed_by", None)
            if actor is not None:
                self.reviewed_by_name = actor.get_full_name() or actor.get_username()
            self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"legacy-grade-review<{self.fact_id}:{self.decision}>"


__all__ = [
    "LegacyGradeArtifact",
    "LegacyGradeArtifactKind",
    "LegacyGradeEvidenceKind",
    "LegacyGradeFact",
    "LegacyGradeMappingStatus",
    "LEGACY_GRADE_REVIEW_PERMISSION",
    "LegacyGradeReview",
    "LegacyGradeReviewDecision",
]
