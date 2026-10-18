"""25% / alt qrup müraciətinin APPEND-ONLY izləri — hadisə jurnalı, qəbzlər, imtahan şansı qeydləri.

Üç cədvəlin hamısı ``ImmutableCorrectionEvidence``-dən miras alır (tətbiq qatı: ``save()`` yalnız ilk
dəfə, ``delete()`` qadağan) və ``0091`` migrasiyasının PostgreSQL trigger-i UPDATE / DELETE / TRUNCATE-i
bloklayır (xam SQL / ``QuerySet.update()`` üçün son sədd).

* ``RetakeApplicationEvent`` — hər status keçidi və hər qərar: kim, nə vaxt, haradan → haraya, qeyd.
* ``RetakeReceipt`` — hər yüklənən qəbz AYRI sətirdir (rədd → yenidən yükləmədə köhnəsi itmir); SHA-256 +
  ölçü saxlanılır ki, eyni qəbzin başqa müraciətdə də yüklənməsi Mühasibatlığa göstərilsin.
* ``ExamChanceGrant`` — «İmtahan şansı ver» əməlinin rəsmi qeydi (səbəb növü, əmr №/tarix, qeyd). Exams
  modulu registrar-ı import edir, əksinə yox — imtahan ``exam_id`` + başlıq snapshot-u ilə saxlanılır.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from .corrections import ImmutableCorrectionEvidence
from .retake import RetakeStatus, retake_file_validators, retake_receipt_path

_CTX = "registrar.retake"


class RetakeEventAction(models.TextChoices):
    SUBMITTED = "submitted", pgettext_lazy(_CTX, "Müraciət göndərildi")
    RECEIPT_UPLOADED = "receipt_uploaded", pgettext_lazy(_CTX, "Qəbz yükləndi")
    PAYMENT_VERIFIED = "payment_verified", pgettext_lazy(_CTX, "Ödəniş təsdiqləndi")
    PAYMENT_REJECTED = "payment_rejected", pgettext_lazy(_CTX, "Qəbz rədd edildi")
    ADMITTED = "admitted", pgettext_lazy(_CTX, "İmtahana buraxıldı")
    SUBGROUP_APPROVED = "subgroup_approved", pgettext_lazy(_CTX, "Alt qrup təsdiqləndi")
    PLACED = "placed", pgettext_lazy(_CTX, "Alt qrupa yerləşdirildi")
    REJECTED = "rejected", pgettext_lazy(_CTX, "Rədd edildi")
    EXAM_GRANTED = "exam_granted", pgettext_lazy(_CTX, "İmtahan cəhdi verildi")
    RESULT_RECORDED = "result_recorded", pgettext_lazy(_CTX, "Nəticə yazıldı")
    WITHDRAWN = "withdrawn", pgettext_lazy(_CTX, "Geri götürüldü")
    NO_SHOW = "no_show", pgettext_lazy(_CTX, "İmtahana gəlmədi")
    #: 2026-10-19 (sahib): ödənişin qaytarılması — rəsmi qərar və Mühasibatlığın icra qeydi (``retake_refund``).
    REFUND_DECIDED = "refund_decided", pgettext_lazy(_CTX, "Ödənişin qaytarılması qərarı verildi")
    REFUNDED = "refunded", pgettext_lazy(_CTX, "Ödəniş qaytarıldı")


class RetakeActorRole(models.TextChoices):
    STUDENT = "student", pgettext_lazy(_CTX, "Tələbə")
    ACCOUNTING = "accounting", pgettext_lazy(_CTX, "Mühasibatlıq")
    DEANERY = "deanery", pgettext_lazy(_CTX, "Dekanlıq / tədris şöbəsi")
    EXAM_CENTER = "exam_center", pgettext_lazy(_CTX, "İmtahan mərkəzi")
    SYSTEM = "system", pgettext_lazy(_CTX, "Sistem")


class RetakeApplicationEvent(ImmutableCorrectionEvidence):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="+")
    application = models.ForeignKey("registrar.RetakeApplication", on_delete=models.PROTECT, related_name="events")
    action = models.CharField(max_length=24, choices=RetakeEventAction.choices)
    from_status = models.CharField(max_length=24, choices=RetakeStatus.choices, blank=True)
    to_status = models.CharField(max_length=24, choices=RetakeStatus.choices, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    actor_name = models.CharField(max_length=200, blank=True)
    actor_role = models.CharField(max_length=16, choices=RetakeActorRole.choices, default=RetakeActorRole.SYSTEM)
    note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    objects = models.Manager()

    class Meta:
        ordering = ["created_at"]
        verbose_name = pgettext_lazy("registrar.model.retake_event.meta", "retake application event")
        verbose_name_plural = pgettext_lazy("registrar.model.retake_event.meta", "retake application events")
        indexes = [models.Index(fields=["organization", "application", "created_at"], name="reg_retake_ev_app_idx")]

    def __str__(self):
        return f"retake-event<{self.application_id}> {self.action} {self.from_status}->{self.to_status}"


class RetakeReceipt(ImmutableCorrectionEvidence):
    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="+")
    application = models.ForeignKey("registrar.RetakeApplication", on_delete=models.PROTECT, related_name="receipts")
    file = models.FileField(upload_to=retake_receipt_path, max_length=200, validators=retake_file_validators())
    sha256 = models.CharField(max_length=64)
    size = models.PositiveBigIntegerField(default=0)
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.retake_receipt.meta", "retake payment receipt")
        verbose_name_plural = pgettext_lazy("registrar.model.retake_receipt.meta", "retake payment receipts")
        indexes = [models.Index(fields=["organization", "sha256"], name="reg_retake_rc_hash_idx")]

    def __str__(self):
        return f"retake-receipt<{self.application_id}> {self.sha256[:12]}"


class ExamChanceReason(models.TextChoices):
    RETAKE_25 = "retake_25", pgettext_lazy(_CTX, "25% müraciəti")
    UNIVERSITY = "university", pgettext_lazy(_CTX, "Universitet güzəşti")
    TECHNICAL = "technical", pgettext_lazy(_CTX, "Texniki problem")
    APPEAL = "appeal", pgettext_lazy(_CTX, "Apellyasiya qərarı")
    OTHER = "other", pgettext_lazy(_CTX, "Digər")


class ExamChanceGrant(ImmutableCorrectionEvidence):
    """«İmtahan şansı ver» — bir tələbəyə bir imtahan üzrə verilən əlavə cəhdin rəsmi qeydi."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.PROTECT, related_name="+")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="exam_chance_grants")
    subject = models.ForeignKey("registrar.Subject", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    exam_id = models.PositiveBigIntegerField()
    exam_title = models.CharField(max_length=300, blank=True)
    exam_type = models.CharField(max_length=20, blank=True, help_text="test / written / coding (praktiki).")
    exam_category = models.CharField(max_length=20, blank=True, help_text="final / midterm.")
    reason = models.CharField(max_length=16, choices=ExamChanceReason.choices)
    reference_number = models.CharField(max_length=80, blank=True)
    reference_date = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)
    application = models.ForeignKey(
        "registrar.RetakeApplication", null=True, blank=True, on_delete=models.PROTECT, related_name="chance_grants"
    )
    extra_attempts = models.PositiveSmallIntegerField(default=1)
    granted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    granted_by_name = models.CharField(max_length=200, blank=True)

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.exam_chance_grant.meta", "exam chance grant")
        verbose_name_plural = pgettext_lazy("registrar.model.exam_chance_grant.meta", "exam chance grants")
        indexes = [
            models.Index(fields=["organization", "-created_at"], name="reg_chance_org_created_idx"),
            models.Index(fields=["organization", "student", "exam_id"], name="reg_chance_student_exam_idx"),
        ]

    def __str__(self):
        return f"exam-chance<{self.student_id}:{self.exam_id}> {self.reason}"


__all__ = [
    "ExamChanceGrant",
    "ExamChanceReason",
    "RetakeActorRole",
    "RetakeApplicationEvent",
    "RetakeEventAction",
    "RetakeReceipt",
]
