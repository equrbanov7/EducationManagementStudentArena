"""«Elanlar» modelləri — elan, əlavə sənəd, istifadəçi qəbzi.

Üç cədvəlin hamısında ``organization_id`` var və RLS ``rls_tenant_isolation`` siyasəti
ilə qorunur (miqrasiya 0002). Auditoriya iki JSON siyahısıdır (``audience_families`` —
``students``/``teachers``/``staff``; ``audience_units`` — ``OrgUnit`` id-ləri, boş = bütün
təşkilat). PostgreSQL-də ``?|`` (``has_any_keys``) operatoru ilə süzülür — istifadəçinin
ailələri və bölmə ƏCDADLARI ilə kəsişmə (bax ``services/audience.visible_q``).
"""

from __future__ import annotations

import os
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel
from core.upload_security import FileUploadValidator

from .constants import (
    ATTACHMENT_EXTENSIONS,
    ATTACHMENT_MAX_MB,
    STATE_ACTIVE,
    STATE_DELETED,
    STATE_EXPIRED,
    STATE_SCHEDULED,
    SUMMARY_MAX,
    TITLE_MAX,
    URL_MAX,
    ApplyMode,
    Category,
    Priority,
    Status,
)

_CTX = "announcements.model"


class Announcement(UUIDModel, TimeStampedModel):
    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="announcements"
    )
    title = models.CharField(max_length=TITLE_MAX)
    summary = models.CharField(max_length=SUMMARY_MAX, blank=True, default="")
    #: Düz mətn — şablonda ``linebreaks``/``urlize`` ilə (avtomatik escape) göstərilir; HTML saxlanılmır.
    body = models.TextField(blank=True, default="")
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.GENERAL)
    priority = models.PositiveSmallIntegerField(choices=Priority.choices, default=Priority.NORMAL)
    is_pinned = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    #: Görünmə pəncərəsi: ``publish_at`` ≤ indi < ``expires_at`` (boş → müddətsiz).
    publish_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    #: «Son tarix» — məs. müraciətin qəbulu; keçəndən sonra «Müraciət et» bağlanır.
    deadline_at = models.DateTimeField(null=True, blank=True)
    show_as_popup = models.BooleanField(default=False)
    #: Məcburi tanışlıq (2026-10-07): popup bağlana bilmir, istifadəçi «Tanış oldum» təsdiqi
    #: verənədək (``AnnouncementReceipt.acknowledged_at``) hər tam səhifədə çıxır. Popup-u nəzərdə
    #: tutur — ``ann_ack_needs_popup`` CHECK-i və forma/servis bunu təmin edir.
    requires_ack = models.BooleanField(default=False, db_default=False)
    audience_families = models.JSONField(default=list, blank=True)
    audience_units = models.JSONField(default=list, blank=True)
    apply_mode = models.CharField(max_length=12, choices=ApplyMode.choices, default=ApplyMode.NONE)
    apply_kind = models.ForeignKey(
        "applications.ApplicationKind", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: Boşdursa müraciət növün öz marşrutu ilə gedir; doludursa bu şöbəyə.
    apply_unit = models.ForeignKey(
        "applications.ApplicationUnit", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    apply_url = models.CharField(max_length=URL_MAX, blank=True, default="")
    apply_label = models.CharField(max_length=60, blank=True, default="")
    published_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: Yumşaq silmə (sahib, 2026-10-07): sətir, qəbzlər (statistika) və sənədlər audit üçün qalır,
    #: lakin elan BÜTÜN istifadəçi səthlərindən (siyahı, detal, popup, sayğac, müraciət) çıxır.
    #: Menecer «Silinmişlər» filtrindən bərpa edir (→ qaralama). Qəbzsiz qaralama isə birdəfəlik silinir.
    is_deleted = models.BooleanField(default=False, db_default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "elan")
        verbose_name_plural = pgettext_lazy(_CTX, "elanlar")
        ordering = ["-is_pinned", "-publish_at", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "status", "-publish_at"], name="ann_org_status_pub"),
            models.Index(fields=["organization", "deadline_at"], name="ann_org_deadline"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(expires_at__isnull=True)
                | models.Q(publish_at__isnull=True)
                | models.Q(expires_at__gt=models.F("publish_at")),
                name="ann_window_ordered",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=[choice.value for choice in Status]), name="ann_status_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(is_deleted=False) | models.Q(deleted_at__isnull=False),
                name="ann_deleted_has_time",
            ),
            models.CheckConstraint(
                condition=models.Q(requires_ack=False) | models.Q(show_as_popup=True),
                name="ann_ack_needs_popup",
            ),
        ]

    def __str__(self):
        return f"announcement<{self.status}:{self.title[:40]}>"

    def effective_state(self, now=None) -> str:
        """``deleted`` / ``draft`` / ``archived`` / ``scheduled`` / ``active`` / ``expired`` (tarixdən asılı)."""
        if self.is_deleted:
            return STATE_DELETED
        if self.status != Status.PUBLISHED:
            return self.status
        now = now or timezone.now()
        if self.publish_at and self.publish_at > now:
            return STATE_SCHEDULED
        if self.expires_at and self.expires_at <= now:
            return STATE_EXPIRED
        return STATE_ACTIVE

    def is_visible_now(self, now=None) -> bool:
        return self.effective_state(now) == STATE_ACTIVE

    @property
    def has_apply(self) -> bool:
        return self.apply_mode in (ApplyMode.INTERNAL, ApplyMode.URL)

    def deadline_passed(self, now=None) -> bool:
        return bool(self.deadline_at and self.deadline_at <= (now or timezone.now()))


def announcement_attachment_path(instance, filename: str) -> str:
    """``announcements/<org>/<announcement>/<uuid><ext>`` — orijinal ad diskə yazılmır (PII/traversal)."""
    extension = os.path.splitext(filename or "")[1].lower()[:10]
    return f"announcements/{instance.organization_id}/{instance.announcement_id}/{uuid.uuid4().hex}{extension}"


class AnnouncementAttachment(UUIDModel, TimeStampedModel):
    """Elana əlavə sənəd — yalnız icazə qapılı endirmə ilə verilir (``views/user.attachment_download``)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(
        max_length=255,
        upload_to=announcement_attachment_path,
        validators=[FileUploadValidator(allowed_extensions=set(ATTACHMENT_EXTENSIONS), max_size_mb=ATTACHMENT_MAX_MB)],
    )
    original_name = models.CharField(max_length=255)
    size = models.PositiveIntegerField(default=0)
    content_type = models.CharField(max_length=120, blank=True, default="")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "elan sənədi")
        verbose_name_plural = pgettext_lazy(_CTX, "elan sənədləri")
        ordering = ["created_at"]

    def __str__(self):
        return self.original_name


class AnnouncementReceipt(UUIDModel, TimeStampedModel):
    """İstifadəçi × elan: popup görülüb, oxunub, təsdiq edilib, müraciət edilib (hər cüt üçün BİR sətir)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="+")
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="receipts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    popup_seen_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    #: Məcburi elanla «Elanı oxudum və tanış oldum» təsdiqi (yalnız ``requires_ack`` elanlarda yazılır).
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    #: Daxili müraciətin id-si / nömrəsi (FK deyil — modul sərhədi; müraciət öz modulunda yaşayır).
    application_id = models.UUIDField(null=True, blank=True)
    application_number = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "elan qəbzi")
        verbose_name_plural = pgettext_lazy(_CTX, "elan qəbzləri")
        constraints = [
            models.UniqueConstraint(fields=["announcement", "user"], name="ann_receipt_once"),
        ]
        indexes = [models.Index(fields=["organization", "user"], name="ann_receipt_org_user")]

    def __str__(self):
        return f"receipt<{self.announcement_id}:{self.user_id}>"
