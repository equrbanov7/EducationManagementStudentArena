"""Zaman xətti (append-only), izləmə abunəsi və sənəd əlavələri."""

from __future__ import annotations

import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel
from core.upload_security import FileUploadValidator

from ..constants import ALLOWED_ATTACHMENT_EXTENSIONS, MAX_ATTACHMENT_MB, ApplicationStatus, EventKind

_CTX = "applications"


def application_attachment_path(instance, filename: str) -> str:
    """``applications/<org_id>/<application_id>/<uuid><ext>`` — org-scoped.

    Orijinal ad QƏSDƏN diskə yazılmır: istifadəçi adı (PII) və traversal riski
    fayl sistemindən uzaq qalır; göstərmək üçün ``original_name`` sahəsi var.
    """
    extension = os.path.splitext(filename or "")[1].lower()[:10]
    return (
        f"applications/{instance.application.organization_id}/{instance.application_id}/{uuid.uuid4().hex}{extension}"
    )


class ApplicationEvent(UUIDModel, TimeStampedModel):
    """Bir keçid / qeyd — YALNIZ əlavə olunur, dəyişdirilmir.

    Tətbiq qatı qoruyucusu ``ImmutableCorrectionEvidence`` ilə eyni fəlsəfədir
    (bax ``apps/registrar/models/corrections.py``): sətir yaradıldıqdan sonra
    ``save()`` və ``delete()`` xəta verir.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="application_events",
    )
    application = models.ForeignKey(
        "applications.Application",
        on_delete=models.CASCADE,
        related_name="events",
    )
    kind = models.CharField(max_length=20, choices=EventKind.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="application_events",
    )
    #: Ad + rol snapshot-u — istifadəçi sonradan silinsə də tarixçə oxunaqlı qalır.
    actor_name = models.CharField(max_length=200, blank=True, default="", editable=False)
    actor_role_name = models.CharField(max_length=100, blank=True, default="")
    from_unit = models.ForeignKey(
        "applications.ApplicationUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events_from",
    )
    to_unit = models.ForeignKey(
        "applications.ApplicationUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events_to",
    )
    old_status = models.CharField(max_length=20, choices=ApplicationStatus.choices, blank=True, default="")
    new_status = models.CharField(max_length=20, choices=ApplicationStatus.choices, blank=True, default="")
    text = models.TextField(blank=True, default="")
    is_internal = models.BooleanField(
        default=False,
        help_text="Yalnız emalçılar görür — müraciət sahibinə göstərilmir.",
    )

    objects = models.Manager()

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["organization", "application", "created_at"]),
        ]
        verbose_name = pgettext_lazy(_CTX, "müraciət hadisəsi")
        verbose_name_plural = pgettext_lazy(_CTX, "müraciət hadisələri")

    def __str__(self):
        return f"{self.application_id} · {self.kind}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Application events are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Application events cannot be deleted.")


class ApplicationWatch(UUIDModel, TimeStampedModel):
    """«İzləməkdə davam edim» — yönləndirən şöbənin abunəsi.

    Şöbə + aidiyyət bölməsi cütü saxlanır (müraciətin özü artıq başqa şöbədədir),
    yəni izləmə hüququ yönləndirmə ANINDAKI əhatəyə görə qiymətləndirilir.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="application_watches",
    )
    application = models.ForeignKey(
        "applications.Application",
        on_delete=models.CASCADE,
        related_name="watches",
    )
    unit = models.ForeignKey(
        "applications.ApplicationUnit",
        on_delete=models.CASCADE,
        related_name="watches",
    )
    scope_unit = models.ForeignKey(
        "organizations.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="application_watches",
    )

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["application", "unit"], name="uniq_application_watch"),
        ]
        indexes = [models.Index(fields=["organization", "unit"])]
        verbose_name = pgettext_lazy(_CTX, "müraciət izləməsi")
        verbose_name_plural = pgettext_lazy(_CTX, "müraciət izləmələri")

    def __str__(self):
        return f"{self.application_id} ← {self.unit_id}"


class ApplicationAttachment(UUIDModel, TimeStampedModel):
    """Müraciətə və ya bir hadisəyə əlavə olunmuş sənəd.

    Fayl BİRBAŞA ``.url`` ilə verilmir — ``views.downloads`` icazə yoxlayan
    ``FileResponse`` qapısıdır (bax modul README / API müqaviləsi).
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="application_attachments",
    )
    application = models.ForeignKey(
        "applications.Application",
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    event = models.ForeignKey(
        ApplicationEvent,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attachments",
    )
    file = models.FileField(
        upload_to=application_attachment_path,
        validators=[
            FileUploadValidator(
                allowed_extensions=set(ALLOWED_ATTACHMENT_EXTENSIONS),
                max_size_mb=MAX_ATTACHMENT_MB,
            )
        ],
    )
    original_name = models.CharField(max_length=255)
    size = models.PositiveIntegerField(default=0)
    content_type = models.CharField(max_length=120, blank=True, default="")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="application_attachments",
    )

    objects = models.Manager()

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["organization", "application"])]
        verbose_name = pgettext_lazy(_CTX, "müraciət sənədi")
        verbose_name_plural = pgettext_lazy(_CTX, "müraciət sənədləri")

    def __str__(self):
        return self.original_name
