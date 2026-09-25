"""Tədris materialları — fayl, şəkil, kod nümunəsi, keçid, video keçidi, qeyd.

Kod nümunələri FAYL KİMİ DEYİL, MƏTN kimi saxlanılır: ``core.upload_security``
``.js/.html/.svg/.sh`` yükləməsini (haqlı olaraq) bloklayır, müəllim isə məhz
belə nümunələr paylaşır. Mətn heç vaxt icra olunmur — UI onu escape edilmiş
``<pre>`` kimi göstərir.

Fayl ``file.url`` ilə VERİLMİR (S3 imzalı URL icazə yoxlamasını keçərdi) —
yükləmə ``views.material_download`` və ya ``core.media_urls.protected_media_url``
ilə gedir; icazə ``services.access.can_view_material``-dadır.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy

from core.models import TimeStampedModel, UUIDModel

from ..constants import CodeLanguage, MaterialKind
from .folder import FolderTopic, SubjectFolder
from .paths import material_file_path

_CTX = "subject_folder.model"


class FolderMaterial(UUIDModel, TimeStampedModel):
    """Qovluğun bir materialı (mövzuya bağlı və ya ümumi)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.CASCADE, related_name="subject_folder_materials"
    )
    folder = models.ForeignKey(SubjectFolder, on_delete=models.CASCADE, related_name="materials")
    topic = models.ForeignKey(FolderTopic, null=True, blank=True, on_delete=models.SET_NULL, related_name="materials")
    kind = models.CharField(max_length=16, choices=MaterialKind.choices)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to=material_file_path, max_length=255, blank=True)
    original_name = models.CharField(max_length=255, blank=True, default="")
    size = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=120, blank=True, default="")
    sha256 = models.CharField(max_length=64, blank=True, default="", db_index=True)
    url = models.URLField(max_length=1000, blank=True, default="")
    code_text = models.TextField(blank=True, default="")
    code_language = models.CharField(max_length=16, choices=CodeLanguage.choices, blank=True, default="")
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=False, db_index=True)
    is_archived = models.BooleanField(default=False, help_text="Silinmiş (gizlədilmiş) material — data saxlanılır.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = models.Manager()

    class Meta:
        verbose_name = pgettext_lazy(_CTX, "tədris materialı")
        verbose_name_plural = pgettext_lazy(_CTX, "tədris materialları")
        ordering = ["folder", "topic", "order", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(kind__in=[MaterialKind.FILE, MaterialKind.IMAGE]) | ~Q(file=""),
                name="sf_material_file_kinds_have_file",
            ),
            models.CheckConstraint(
                condition=~Q(kind__in=[MaterialKind.LINK, MaterialKind.VIDEO_LINK]) | ~Q(url=""),
                name="sf_material_link_kinds_have_url",
            ),
            models.CheckConstraint(
                condition=~Q(kind=MaterialKind.CODE) | ~Q(code_text=""),
                name="sf_material_code_has_text",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "folder", "topic", "order"], name="sf_material_org_folder_topic"),
            models.Index(fields=["folder", "is_published", "is_archived"], name="sf_material_visibility"),
        ]

    def __str__(self):
        return self.title

    @property
    def has_file(self) -> bool:
        return bool(self.file)


__all__ = ["FolderMaterial"]
