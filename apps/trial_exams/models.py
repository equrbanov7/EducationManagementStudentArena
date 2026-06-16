"""Trial-exam request persistence model.

A *trial exam* (``sınaq imtahanı``) is a free, unlimited practice exam a
student can request for themselves: they upload a PDF of questions and the
EMSArena team imports it into the platform during the day. Once imported,
the student receives an email confirmation ("questions added").

The model is intentionally outside the multi-tenant scope (no organization
FK) — exactly like :class:`apps.contact.models.ContactMessage`. A trial
request is an inbound, lead-style submission: the submitter is a logged-in
user, but the request does not belong to any single organization's data and
therefore is not governed by row-level tenant isolation.

Reply tracking lives on the same row (who confirmed, when, delivery status,
body) so there is one complete audit trail per request. The reply flow
mirrors the contact app so the Django admin reply action can be reused.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.upload_security import FileUploadValidator


def trial_questions_upload_path(instance: "TrialExamRequest", filename: str) -> str:
    """Return the storage path for an uploaded questions PDF.

    Files are partitioned by year/month. The actual filename is randomised by
    the service layer before save (see ``randomize_uploaded_filename``); the
    human-readable original name is preserved in ``original_filename``.
    """
    return f"trial_exams/{filename}"


class TrialExamRequest(models.Model):
    # ---- Lifecycle ----
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_ADDED = "added"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, _("Gözləyir")),
        (STATUS_PROCESSING, _("Hazırlanır")),
        (STATUS_ADDED, _("Sistemə əlavə olundu")),
        (STATUS_REJECTED, _("Rədd edildi")),
    ]

    REPLY_FROM_CHOICES = [
        ("info", _("info@emsarena.com")),
        ("support", _("support@emsarena.com")),
    ]

    REPLY_DELIVERY_PENDING = "pending"
    REPLY_DELIVERY_SENT = "sent"
    REPLY_DELIVERY_FAILED = "failed"
    REPLY_DELIVERY_RECORDED = "recorded"
    REPLY_DELIVERY_STATUS_CHOICES = [
        (REPLY_DELIVERY_PENDING, _("Göndərilir")),
        (REPLY_DELIVERY_SENT, _("Göndərildi")),
        (REPLY_DELIVERY_FAILED, _("Göndərilmədi")),
        (REPLY_DELIVERY_RECORDED, _("Qeyd edildi")),
    ]

    # ---- Submitter ----
    # Login is required to submit, but the row survives the user being deleted
    # so the audit trail and the uploaded PDF are never orphaned.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trial_exam_requests",
        verbose_name=_("İstifadəçi"),
    )
    full_name = models.CharField(_("Ad Soyad"), max_length=120)
    email = models.EmailField(_("Email"), max_length=254)
    subject_name = models.CharField(_("Fənnin adı"), max_length=150)
    note = models.TextField(_("Qeyd"), max_length=2000, blank=True)

    questions_file = models.FileField(
        _("Suallar (PDF)"),
        upload_to=trial_questions_upload_path,
        validators=[FileUploadValidator(allowed_extensions={".pdf"})],
    )
    original_filename = models.CharField(_("Orijinal fayl adı"), max_length=255, blank=True)

    status = models.CharField(
        _("Status"),
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    # ---- Metadata (staff-only) ----
    ip_address = models.GenericIPAddressField(_("IP ünvan"), null=True, blank=True)
    user_agent = models.CharField(_("User-Agent"), max_length=512, blank=True)
    is_handled = models.BooleanField(_("Cavablandırılıb"), default=False)

    created_at = models.DateTimeField(_("Göndərilmə tarixi"), auto_now_add=True)
    handled_at = models.DateTimeField(_("Cavab tarixi"), null=True, blank=True)

    # ---- Reply tracking (mirrors ContactMessage) ----
    reply_body = models.TextField(_("Cavab mətni"), blank=True, max_length=10000)
    reply_from = models.CharField(
        _("Hansı maildən"),
        max_length=16,
        choices=REPLY_FROM_CHOICES,
        blank=True,
    )
    reply_delivery_status = models.CharField(
        _("Cavab email statusu"),
        max_length=16,
        choices=REPLY_DELIVERY_STATUS_CHOICES,
        blank=True,
    )
    reply_delivery_error = models.CharField(_("Cavab email xətası"), max_length=500, blank=True)
    reply_sent_at = models.DateTimeField(_("Cavab göndərilmə tarixi"), null=True, blank=True)
    reply_sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trial_exam_replies",
        verbose_name=_("Cavab verən admin"),
    )

    class Meta:
        verbose_name = _("Sınaq imtahanı sorğusu")
        verbose_name_plural = _("Sınaq imtahanı sorğuları")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["is_handled", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}> — {self.subject_name}"

    @property
    def has_been_replied(self) -> bool:
        return bool(self.reply_sent_at)

    @property
    def reply_delivery_failed(self) -> bool:
        return self.reply_delivery_status == self.REPLY_DELIVERY_FAILED

    @property
    def reply_delivery_pending(self) -> bool:
        return self.reply_delivery_status == self.REPLY_DELIVERY_PENDING
