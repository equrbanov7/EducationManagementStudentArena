"""«25%» təkrar imtahan və alt qrup müraciəti — sahib 2026-10-18.

Sahib: «Tələbənin 25% müraciətini edəcək yer olsun… hansı fəndən 25% verə bilərsə, o görünsün. Sonra alt
qrupa da. Orda çek yükləmək üçün yer olsun. Bütün addımlar yadda saxlanılsın — neçə dəfə 25%-ə girib, nə
olub. Tələbə ola bilər 25 vermədən alt qrupa qalmaq istədi».

Model qərarları
---------------
* ``RetakeApplication`` — bir tələbənin BİR kəsr fənn üzrə BİR müraciəti (növ: ``retake_25`` və ya
  ``subgroup``). Status maşını :mod:`apps.registrar.retake_rules`-dadır; keçidlər YALNIZ servis
  qatından (:mod:`apps.registrar.retake_services`) gedir və hər keçid append-only
  ``RetakeApplicationEvent`` sətri yazır (``retake_log``).
* Uyğunluğun «niyə»si müraciət anında ``eligibility`` (JSON) snapshot-una DONDURULUR — sonradan qayda
  dəyişsə də qərarın əsası görünür. ``base_exam_score`` / ``base_total`` — «Əsas imtahan: 32 → 25%: 61»
  sətrinin sol tərəfi (əsas imtahan balı sonradan üzərinə yazılsa belə itmir).
* Nəticə ``ResitRecord``-a yazılır (``compute_final_result``-un mövcud qaydası: tamamlanmış təkrar imtahan
  balı əsas imtahan balını əvəz edir) — müraciətin öz ``result_*`` sahələri hər cəhdin balını ayrıca
  saxlayır, ona görə ``ResitRecord`` (bir qeydiyyata bir sətir) yalnız SONUNCU (qüvvədə olan) balı daşıyır.
* Bir fənn üzrə eyni anda yalnız BİR aktiv müraciət — qismən unikal məhdudiyyət (yarış halına qarşı).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel
from core.upload_security import FileUploadValidator

_CTX = "registrar.retake"

#: Qəbz / qərar sənədi — PDF və ya şəkil (sahib: «çek yükləmək üçün yer»), 10 MB.
RETAKE_FILE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
RETAKE_FILE_MAX_MB = 10

#: Qorunan media prefiksləri (``apps.registrar.apps`` ``register_media_policy`` ilə qeyd edir).
RETAKE_RECEIPT_PREFIX = "retake_receipts/"
RETAKE_DOCUMENT_PREFIX = "retake_documents/"


def _random_name(filename: str) -> str:
    import posixpath
    from uuid import uuid4

    extension = posixpath.splitext(str(filename or ""))[1].lower()
    if extension not in RETAKE_FILE_EXTENSIONS:
        extension = ""
    return f"{uuid4().hex}{extension}"


def retake_receipt_path(instance, filename: str) -> str:
    """``retake_receipts/<org>/<təsadüfi ad>`` — orijinal ad ayrıca sahədə saxlanılır, yolda yox."""
    return f"{RETAKE_RECEIPT_PREFIX}{instance.organization_id}/{_random_name(filename)}"


def retake_document_path(instance, filename: str) -> str:
    """Dekanlığın qərar sənədi (alt qrup təqdimatı) — org-scoped, təsadüfi ad."""
    return f"{RETAKE_DOCUMENT_PREFIX}{instance.organization_id}/{_random_name(filename)}"


def retake_file_validators():
    return [FileUploadValidator(allowed_extensions=RETAKE_FILE_EXTENSIONS, max_size_mb=RETAKE_FILE_MAX_MB)]


class RetakeKind(models.TextChoices):
    RETAKE_25 = "retake_25", pgettext_lazy(_CTX, "25% təkrar imtahan")
    SUBGROUP = "subgroup", pgettext_lazy(_CTX, "Alt qrupda yenidən keçmək")


class RetakeStatus(models.TextChoices):
    SUBMITTED = "submitted", pgettext_lazy(_CTX, "Göndərilib")
    PAYMENT_PENDING_REVIEW = "payment_pending_review", pgettext_lazy(_CTX, "Ödəniş yoxlanılır")
    PAYMENT_REJECTED = "payment_rejected", pgettext_lazy(_CTX, "Qəbz rədd edilib")
    PAYMENT_VERIFIED = "payment_verified", pgettext_lazy(_CTX, "Ödəniş təsdiqlənib")
    ADMITTED = "admitted", pgettext_lazy(_CTX, "Buraxılıb")
    EXAM_GRANTED = "exam_granted", pgettext_lazy(_CTX, "İmtahan cəhdi verilib")
    COMPLETED = "completed", pgettext_lazy(_CTX, "Tamamlanıb")
    REJECTED = "rejected", pgettext_lazy(_CTX, "Rədd edilib")
    WITHDRAWN = "withdrawn", pgettext_lazy(_CTX, "Geri götürülüb")
    #: 2026-10-19 (sahib): ödənişdən sonra imtahana gəlməyib — cəhd İSTİFADƏ OLUNMUŞ sayılır (rəsmi qərarla).
    NO_SHOW = "no_show", pgettext_lazy(_CTX, "İmtahana gəlmədi")


#: Aktiv (bitməmiş) statuslar — bir fənn üzrə yalnız biri ola bilər.
ACTIVE_STATUSES = (
    RetakeStatus.SUBMITTED,
    RetakeStatus.PAYMENT_PENDING_REVIEW,
    RetakeStatus.PAYMENT_REJECTED,
    RetakeStatus.PAYMENT_VERIFIED,
    RetakeStatus.ADMITTED,
    RetakeStatus.EXAM_GRANTED,
)

#: 25% cəhdini «istifadə olunmuş» sayan statuslar (cəhd limiti bunlardan hesablanır).
CONSUMED_STATUSES = (RetakeStatus.ADMITTED, RetakeStatus.EXAM_GRANTED, RetakeStatus.COMPLETED, RetakeStatus.NO_SHOW)


class RetakeResultSource(models.TextChoices):
    MANUAL = "manual", pgettext_lazy(_CTX, "Dekanlıq daxil edib")
    EXAM_ENTRY = "exam_entry", pgettext_lazy(_CTX, "İmtahan balından")


class RetakeApplication(UUIDModel, TimeStampedModel):
    """Bir kəsr fənn üzrə 25% / alt qrup müraciəti (status maşını — ``retake_rules``)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="retake_applications"
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="retake_applications")
    enrollment = models.ForeignKey("registrar.Enrollment", on_delete=models.PROTECT, related_name="retake_applications")
    subject = models.ForeignKey("registrar.Subject", on_delete=models.PROTECT, related_name="retake_applications")
    period = models.ForeignKey(
        "organizations.AcademicPeriod", on_delete=models.PROTECT, related_name="retake_applications"
    )
    #: Tələbənin müraciət anındakı akademik qrupu — dekanlıq əhatəsi bununla süzülür.
    student_group = models.ForeignKey(
        "organizations.OrgUnit", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    kind = models.CharField(max_length=16, choices=RetakeKind.choices)
    status = models.CharField(max_length=24, choices=RetakeStatus.choices, default=RetakeStatus.SUBMITTED)
    #: 25% üzrə cəhd nömrəsi (fənn üzrə); alt qrupda 0.
    attempt_number = models.PositiveSmallIntegerField(default=0)
    student_note = models.TextField(blank=True)
    eligibility = models.JSONField(default=dict, blank=True, help_text="Müraciət anında uyğunluğun snapshot-u.")
    base_exam_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    base_total = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    current_receipt = models.ForeignKey(
        "registrar.RetakeReceipt", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: Mühasibatlığın qeyd etdiyi bank arayışı / ödəniş nömrəsi (sərbəst mətn).
    payment_reference = models.CharField(max_length=120, blank=True)
    payment_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    payment_verified_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True)
    decision_document = models.FileField(
        upload_to=retake_document_path, blank=True, max_length=200, validators=retake_file_validators()
    )
    target_offering = models.ForeignKey(
        "registrar.CourseOffering", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    placement_enrollment = models.ForeignKey(
        "registrar.Enrollment", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    resit_record = models.ForeignKey(
        "registrar.ResitRecord", null=True, blank=True, on_delete=models.SET_NULL, related_name="retake_applications"
    )
    exam_granted_at = models.DateTimeField(null=True, blank=True)
    result_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    result_total = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    result_letter = models.CharField(max_length=4, blank=True)
    result_passed = models.BooleanField(null=True, blank=True)
    result_source = models.CharField(max_length=12, choices=RetakeResultSource.choices, blank=True)
    result_recorded_at = models.DateTimeField(null=True, blank=True)
    result_recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    # ── 2026-10-19 (sahib): ödəniş məbləği — gözlənilən (təhsil haqqı cədvəli + düstur) və ödənilən ──────────
    #: Müraciət anında hesablanmış təxmini məbləğ (AZN) və düsturun girişləri (illik haqq, faiz, kredit…).
    expected_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fee_inputs = models.JSONField(default=dict, blank=True)
    #: Mühasibatlığın təsdiq anında yazdığı ödənilmiş məbləğ (AZN); fərq xəbərdarlıqdır, blok deyil.
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # ── Ödənişdən sonra bağlanmanın RƏSMİ qərarı (əmr № + tarix və ya sənəd). Qaytarılma YOXDUR — qayda sahibdən
    #    gözlənilir (bax ``retake_closure``). ────────────────────────────────────────────────────────────────
    closure_order_number = models.CharField(max_length=80, blank=True)
    closure_order_date = models.DateField(null=True, blank=True)
    closure_document = models.FileField(
        upload_to=retake_document_path, blank=True, max_length=200, validators=retake_file_validators()
    )

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.retake.meta", "retake application")
        verbose_name_plural = pgettext_lazy("registrar.model.retake.meta", "retake applications")
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "student", "subject"],
                condition=Q(status__in=[status.value for status in ACTIVE_STATUSES]),
                name="registrar_retake_one_active_per_subject",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status", "-created_at"], name="reg_retake_org_status_idx"),
            models.Index(fields=["organization", "student", "subject"], name="reg_retake_student_subj_idx"),
        ]

    def __str__(self):
        return f"retake<{self.student_id}:{self.subject_id}> {self.kind} {self.status}"

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES


__all__ = [
    "ACTIVE_STATUSES",
    "CONSUMED_STATUSES",
    "RETAKE_DOCUMENT_PREFIX",
    "RETAKE_FILE_EXTENSIONS",
    "RETAKE_FILE_MAX_MB",
    "RETAKE_RECEIPT_PREFIX",
    "RetakeApplication",
    "RetakeKind",
    "RetakeResultSource",
    "RetakeStatus",
    "retake_document_path",
    "retake_file_validators",
    "retake_receipt_path",
]
