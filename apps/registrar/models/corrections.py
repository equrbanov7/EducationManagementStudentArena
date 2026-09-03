"""Jurnal düzəlişləri (üzrlü qayıb / bal korreksiyası) — sənədli audit qeydi.

Superadmin / təşkilat admini (``journal.correct`` icazəsi) müəllimin jurnalına
girib bir xananı (davamiyyət və ya bal) rəsmi sənəd əsasında düzəldir. Hər
düzəliş MÜTLƏQ üç şeylə gəlir: səbəb (seçim), qeyd (mətn) və PDF sənəd
(məs. xəstəlik vərəqəsi). Düzəldənin adı avtomatik profildən götürülür —
əl ilə dəyişdirilə bilməz. Düzəlişli xana müəllim və tələbə jurnallarında
sarı rənglə işarələnir; klik tarixçə modalını açır.

Servis qatı: ``apps/registrar/corrections.py`` (2 saatlıq kilidi
``journal_unlock`` ilə keçir, dəyəri tətbiq edir, audit yazır).
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel
from core.upload_security import FileUploadValidator

from .grading import Lesson, LessonKind, LessonMark

_MAX_DOCUMENT_MB = 10


class ImmutableCorrectionEvidence(UUIDModel, TimeStampedModel):
    """Application-level guard for append-only correction evidence.

    PostgreSQL triggers provide the authoritative bulk/raw-SQL guard.  These
    methods make the same contract explicit on SQLite and for ordinary model
    instance operations.
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Correction evidence is immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Correction evidence cannot be deleted.")


def correction_document_path(instance, filename: str) -> str:
    """Qorunan media altında saxlama yolu (org-scoped)."""
    return f"journal_corrections/{instance.organization_id}/{filename}"


def lesson_correction_document_path(instance, filename: str) -> str:
    """Dərs-səviyyə düzəliş sənədi üçün org-scoped saxlama yolu."""
    return f"journal_lesson_corrections/{instance.organization_id}/{filename}"


def selfwork_correction_document_path(instance, filename: str) -> str:
    return f"journal_selfwork_corrections/{instance.organization_id}/{filename}"


def coursework_correction_document_path(instance, filename: str) -> str:
    return f"journal_coursework_corrections/{instance.organization_id}/{filename}"


def component_correction_document_path(instance, filename: str) -> str:
    return f"journal_component_corrections/{instance.organization_id}/{filename}"


class CorrectionField(models.TextChoices):
    """Xananın hansı hissəsi düzəldilir."""

    ATTENDANCE = "attendance", pgettext_lazy("registrar.correction_field", "Attendance")
    SCORE = "score", pgettext_lazy("registrar.correction_field", "Score")


class CorrectionReason(models.TextChoices):
    """Düzəlişin rəsmi səbəbi (modal-da seçilir)."""

    MEDICAL = "medical", pgettext_lazy("registrar.correction_reason", "Medical certificate")
    OFFICIAL = "official", pgettext_lazy("registrar.correction_reason", "Official leave / permission")
    TECHNICAL = "technical", pgettext_lazy("registrar.correction_reason", "Data-entry error")
    APPEAL = "appeal", pgettext_lazy("registrar.correction_reason", "Appeal decision")
    OTHER = "other", pgettext_lazy("registrar.correction_reason", "Other (see note)")


class ReversalReason(models.TextChoices):
    """PII-free reason codes for append-only reversal evidence."""

    OPERATOR_REVERT = "operator_revert", pgettext_lazy(
        "registrar.correction_reversal_reason",
        "Operator reverted the latest correction",
    )


class JournalCorrection(ImmutableCorrectionEvidence):
    """Bir jurnal xanasına edilən bir rəsmi düzəliş (tam audit qeydi).

    Köhnə/yeni dəyərlər snapshot kimi saxlanır — düzəlişlər zənciri xronoloji
    tarixçə verir. Qeyd + PDF sənəd + səbəb məcburidir (servis qatı yoxlayır).
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="journal_corrections"
    )
    # SET_NULL is intentional: a correction that created a previously-empty
    # cell may be reversed by deleting the fabricated mark, while the signed
    # evidence and stable UUID locators remain append-only.
    lesson_mark = models.ForeignKey(
        LessonMark,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="corrections",
    )
    lesson_mark_ref = models.UUIDField(editable=False, db_index=True)
    lesson_ref = models.UUIDField(editable=False, db_index=True)
    enrollment_ref = models.UUIDField(editable=False, db_index=True)
    field = models.CharField(max_length=12, choices=CorrectionField.choices)
    old_status = models.CharField(max_length=12, blank=True, default="")
    new_status = models.CharField(max_length=12, blank=True, default="")
    old_score = models.IntegerField(null=True, blank=True)
    new_score = models.IntegerField(null=True, blank=True)
    # Boş xanaya (əvvəl mark yox idi) edilən düzəliş LessonMark-ı özü yaradır.
    # Bu bayraq geri almada həmin saxta sətri tam silmək üçün lazımdır ki, xana
    # yenidən BOŞ olsun (uydurma 'iştirak' izi qalmasın).
    created_mark = models.BooleanField(default=False, editable=False)
    reason = models.CharField(max_length=12, choices=CorrectionReason.choices)
    note = models.TextField(help_text="Düzəlişin izahı — tələbə və müəllim görür (məcburi).")
    document = models.FileField(
        upload_to=correction_document_path,
        validators=[FileUploadValidator(allowed_extensions={".pdf"}, max_size_mb=_MAX_DOCUMENT_MB)],
        help_text="Əsas sənəd — yalnız PDF (məcburi).",
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="journal_corrections"
    )
    # Ad profildən avtomatik snapshot-lanır (istifadəçi sonradan silinsə belə
    # tarixçədə kimin düzəltdiyi dəyişməz qalsın deyə).
    corrected_by_name = models.CharField(max_length=200, editable=False)

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.correction.meta", "journal correction")
        verbose_name_plural = pgettext_lazy("registrar.model.correction.meta", "journal corrections")
        indexes = [
            models.Index(fields=["organization", "lesson_mark"]),
            models.Index(fields=["organization", "-created_at"]),
        ]

    def __str__(self):
        return f"correction<{self.lesson_mark_id}> {self.field} ({self.reason})"


class LessonCorrection(ImmutableCorrectionEvidence):
    """Dərs sətrinə (tarix / dərs tipi / saat) edilən rəsmi düzəliş — sənədli.

    İKT Rəhbəri kilidlənmiş (2 saat keçmiş) dərsin tarixini, tipini (mühazirə ↔
    seminar) və ya saatını düzəldəndə bal düzəlişi ilə eyni tələb qüvvədədir:
    səbəb + qeyd + PDF sənəd məcburidir və audit olunur. Köhnə/yeni dəyərlər
    snapshot kimi saxlanır ki, dərs sonra dəyişsə belə tarixçə qalsın.
    """

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="lesson_corrections"
    )
    # SET_NULL (CASCADE deyil): kilidlənmiş dərs SİLİNƏNDƏ də sənədli düzəliş qeydi
    # (kim, niyə, PDF) qalmalıdır — silinmiş dərsin izi itməsin.
    lesson = models.ForeignKey(Lesson, null=True, blank=True, on_delete=models.SET_NULL, related_name="corrections")
    lesson_label = models.CharField(max_length=120, blank=True, default="", help_text="Silinmə üçün dərs snapshotu.")
    is_deletion = models.BooleanField(default=False, help_text="Bu qeyd dərsin silinməsidir (redaktə deyil).")
    old_date = models.DateField(null=True, blank=True)
    new_date = models.DateField(null=True, blank=True)
    old_kind = models.CharField(max_length=16, choices=LessonKind.choices, blank=True, default="")
    new_kind = models.CharField(max_length=16, choices=LessonKind.choices, blank=True, default="")
    old_hours = models.PositiveSmallIntegerField(null=True, blank=True)
    new_hours = models.PositiveSmallIntegerField(null=True, blank=True)
    old_time = models.CharField(max_length=32, blank=True, default="")
    new_time = models.CharField(max_length=32, blank=True, default="")
    old_topic = models.CharField(max_length=255, blank=True, default="")
    new_topic = models.CharField(max_length=255, blank=True, default="")
    old_instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    new_instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reason = models.CharField(max_length=12, choices=CorrectionReason.choices)
    note = models.TextField(help_text="Düzəlişin izahı (məcburi).")
    document = models.FileField(
        upload_to=lesson_correction_document_path,
        validators=[FileUploadValidator(allowed_extensions={".pdf"}, max_size_mb=_MAX_DOCUMENT_MB)],
        help_text="Əsas sənəd — yalnız PDF (məcburi).",
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="lesson_corrections"
    )
    corrected_by_name = models.CharField(max_length=200, editable=False)

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.lesson_correction.meta", "lesson correction")
        verbose_name_plural = pgettext_lazy("registrar.model.lesson_correction.meta", "lesson corrections")
        indexes = [
            models.Index(fields=["organization", "lesson"]),
            models.Index(fields=["organization", "-created_at"]),
        ]

    def __str__(self):
        return f"lesson-correction<{self.lesson_id}> ({self.reason})"


class SelfWorkCorrection(ImmutableCorrectionEvidence):
    """Sərbəst iş xanasına (topic × tələbə: təhvil 0↔1) sənədli düzəliş.

    Bal xanası düzəlişi ilə eyni müqavilə: səbəb + qeyd + PDF məcburi, audit
    olunur, xana sarı işarələnir, geri alına bilər."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="selfwork_corrections"
    )
    topic = models.ForeignKey("registrar.SelfWorkTopic", on_delete=models.PROTECT, related_name="corrections")
    enrollment = models.ForeignKey(
        "registrar.Enrollment", on_delete=models.PROTECT, related_name="selfwork_corrections"
    )
    old_done = models.BooleanField(default=False)
    new_done = models.BooleanField(default=False)
    reason = models.CharField(max_length=12, choices=CorrectionReason.choices)
    note = models.TextField(help_text="Düzəlişin izahı (məcburi).")
    document = models.FileField(
        upload_to=selfwork_correction_document_path,
        validators=[FileUploadValidator(allowed_extensions={".pdf"}, max_size_mb=_MAX_DOCUMENT_MB)],
        help_text="Əsas sənəd — yalnız PDF (məcburi).",
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="selfwork_corrections"
    )
    corrected_by_name = models.CharField(max_length=200, editable=False)

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.selfwork_correction.meta", "self-work correction")
        verbose_name_plural = pgettext_lazy("registrar.model.selfwork_correction.meta", "self-work corrections")
        indexes = [
            models.Index(fields=["organization", "topic", "enrollment"]),
            models.Index(fields=["organization", "-created_at"]),
        ]

    def __str__(self):
        return f"selfwork-correction<{self.topic_id}/{self.enrollment_id}> ({self.reason})"


class CourseWorkCorrection(ImmutableCorrectionEvidence):
    """Kurs işi xanasına (tələbə: bal / mövzu / tarix) sənədli düzəliş — bal
    xanası ilə eyni müqavilə (səbəb + qeyd + PDF, audit, sarı, geri alına bilər)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="coursework_corrections"
    )
    enrollment = models.ForeignKey(
        "registrar.Enrollment", on_delete=models.PROTECT, related_name="coursework_corrections"
    )
    old_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    new_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    old_topic = models.CharField(max_length=255, blank=True, default="")
    new_topic = models.CharField(max_length=255, blank=True, default="")
    old_date = models.DateField(null=True, blank=True)
    new_date = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=12, choices=CorrectionReason.choices)
    note = models.TextField(help_text="Düzəlişin izahı (məcburi).")
    document = models.FileField(
        upload_to=coursework_correction_document_path,
        validators=[FileUploadValidator(allowed_extensions={".pdf"}, max_size_mb=_MAX_DOCUMENT_MB)],
        help_text="Əsas sənəd — yalnız PDF (məcburi).",
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="coursework_corrections"
    )
    corrected_by_name = models.CharField(max_length=200, editable=False)

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.coursework_correction.meta", "course-work correction")
        verbose_name_plural = pgettext_lazy("registrar.model.coursework_correction.meta", "course-work corrections")
        indexes = [
            models.Index(fields=["organization", "enrollment"]),
            models.Index(fields=["organization", "-created_at"]),
        ]

    def __str__(self):
        return f"coursework-correction<{self.enrollment_id}> ({self.reason})"


class ComponentScoreCorrection(ImmutableCorrectionEvidence):
    """Komponent balına (məs. Kollokvium K1/K2/K3 — komponent × tələbə) sənədli
    düzəliş — bal xanası ilə eyni müqavilə (səbəb + qeyd + PDF, audit, sarı, geri
    alına bilər). Müəllim balı səhv yazıbsa İKT rəhbəri düzəldir."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="component_corrections"
    )
    component = models.ForeignKey("registrar.AssessmentComponent", on_delete=models.PROTECT, related_name="corrections")
    enrollment = models.ForeignKey(
        "registrar.Enrollment", on_delete=models.PROTECT, related_name="component_corrections"
    )
    old_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    new_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    reason = models.CharField(max_length=12, choices=CorrectionReason.choices)
    note = models.TextField(help_text="Düzəlişin izahı (məcburi).")
    document = models.FileField(
        upload_to=component_correction_document_path,
        validators=[FileUploadValidator(allowed_extensions={".pdf"}, max_size_mb=_MAX_DOCUMENT_MB)],
        help_text="Əsas sənəd — yalnız PDF (məcburi).",
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="component_corrections"
    )
    corrected_by_name = models.CharField(max_length=200, editable=False)

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.component_correction.meta", "component-score correction")
        verbose_name_plural = pgettext_lazy("registrar.model.component_correction.meta", "component-score corrections")
        indexes = [
            models.Index(fields=["organization", "component", "enrollment"]),
            models.Index(fields=["organization", "-created_at"]),
        ]

    def __str__(self):
        return f"component-correction<{self.component_id}/{self.enrollment_id}> ({self.reason})"


class CorrectionReversal(ImmutableCorrectionEvidence):
    """Append-only evidence that one correction was formally reversed.

    The target is deliberately represented by typed database foreign keys,
    rather than a generic relation, so the database can enforce both existence
    and one-reversal-per-correction.  ``reverted_by_ref`` is an opaque stable
    actor identifier; it preserves attribution if the user row is later
    anonymised/deleted without copying a name or email into this ledger.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="correction_reversals",
    )
    journal_correction = models.OneToOneField(
        JournalCorrection,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversal",
    )
    lesson_correction = models.OneToOneField(
        LessonCorrection,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversal",
    )
    selfwork_correction = models.OneToOneField(
        SelfWorkCorrection,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversal",
    )
    coursework_correction = models.OneToOneField(
        CourseWorkCorrection,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversal",
    )
    component_correction = models.OneToOneField(
        ComponentScoreCorrection,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversal",
    )
    reverted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="correction_reversals",
    )
    reverted_by_ref = models.CharField(max_length=64, editable=False)
    reason_code = models.CharField(
        max_length=32,
        choices=ReversalReason.choices,
        default=ReversalReason.OPERATOR_REVERT,
        editable=False,
    )

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        journal_correction__isnull=False,
                        lesson_correction__isnull=True,
                        selfwork_correction__isnull=True,
                        coursework_correction__isnull=True,
                        component_correction__isnull=True,
                    )
                    | models.Q(
                        journal_correction__isnull=True,
                        lesson_correction__isnull=False,
                        selfwork_correction__isnull=True,
                        coursework_correction__isnull=True,
                        component_correction__isnull=True,
                    )
                    | models.Q(
                        journal_correction__isnull=True,
                        lesson_correction__isnull=True,
                        selfwork_correction__isnull=False,
                        coursework_correction__isnull=True,
                        component_correction__isnull=True,
                    )
                    | models.Q(
                        journal_correction__isnull=True,
                        lesson_correction__isnull=True,
                        selfwork_correction__isnull=True,
                        coursework_correction__isnull=False,
                        component_correction__isnull=True,
                    )
                    | models.Q(
                        journal_correction__isnull=True,
                        lesson_correction__isnull=True,
                        selfwork_correction__isnull=True,
                        coursework_correction__isnull=True,
                        component_correction__isnull=False,
                    )
                ),
                name="reg_rev_exactly_one_target",
            ),
            models.CheckConstraint(
                condition=models.Q(reason_code=ReversalReason.OPERATOR_REVERT),
                name="reg_rev_known_reason_code",
            ),
        ]
        indexes = [models.Index(fields=["organization", "-created_at"], name="reg_rev_org_created_idx")]

    def clean(self):
        super().clean()
        targets = [
            self.journal_correction,
            self.lesson_correction,
            self.selfwork_correction,
            self.coursework_correction,
            self.component_correction,
        ]
        selected = [target for target in targets if target is not None]
        if len(selected) != 1:
            raise ValidationError("A reversal must reference exactly one correction.")
        if selected[0].organization_id != self.organization_id:
            raise ValidationError("A reversal and its correction must belong to the same organization.")
        if self._state.adding and self.reverted_by_id is None:
            raise ValidationError("A reversal actor is required.")
        if self.reverted_by_id is not None and self.reverted_by_ref != str(self.reverted_by_id):
            raise ValidationError("The stable reversal actor reference does not match the actor.")

    def __str__(self):
        return f"correction-reversal<{self.pk}>"
