"""Alt qrupdan əlavənin SƏNƏDİ («təqdimat») — append-only sübut.

SAHİBİN QƏRARI (2026-09-07): tələbə başqa (alt) qrupdan bir jurnala əlavə
ediləndə sənəd yükləmək MƏCBURİDİR — dekanlıq/koordinator təqdimatı, sərəncam
və s. Sənəd əlavə qeydiyyatına (`Enrollment`, `source_group` dolu) bağlanır və
qeydiyyat tarixçəyə keçsə də (`dropped` / `superseded_by`) SİLİNMİR: «alt qrupa
yazılıbsa onun da tarixçəsi qalsın, biz də bilək».

Sətirlər :class:`ImmutableCorrectionEvidence`-dən miras alır — yaradıldıqdan
sonra nə dəyişdirilir, nə silinir (jurnal düzəliş sənədləri ilə eyni zəmanət).
Fayl qorunan media altındadır (`guest_roster_documents/<org>/…`); oxu siyasəti
``core.media_policies.check_guest_roster_document_access``.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import pgettext_lazy

from core.upload_security import FileUploadValidator

from .corrections import ImmutableCorrectionEvidence

#: Sənədin ölçü limiti — jurnal düzəliş sənədləri ilə EYNİ (10 MB).
_MAX_DOCUMENT_MB = 10

#: İcazəli uzantılar: təqdimat/sərəncamın skanı (PDF) və ya fotosu.
GUEST_DOCUMENT_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def guest_document_path(instance, filename: str) -> str:
    """Qorunan media altında org-scoped saxlama yolu."""
    return f"guest_roster_documents/{instance.organization_id}/{filename}"


class GuestRosterDocument(ImmutableCorrectionEvidence):
    """Bir alt-qrup əlavəsinin sənədi (bir qeydiyyata bir neçə sənəd ola bilər)."""

    organization = models.ForeignKey(
        "organizations.Organization", on_delete=models.PROTECT, related_name="guest_roster_documents"
    )
    enrollment = models.ForeignKey("registrar.Enrollment", on_delete=models.PROTECT, related_name="guest_documents")
    document = models.FileField(
        upload_to=guest_document_path,
        validators=[FileUploadValidator(allowed_extensions=GUEST_DOCUMENT_EXTENSIONS, max_size_mb=_MAX_DOCUMENT_MB)],
        help_text="Təqdimat / sərəncam — alt qrupdan əlavənin əsası (məcburi).",
    )
    note = models.CharField(max_length=255, blank=True, help_text="Qısa qeyd (məs. sərəncam №).")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="guest_roster_documents"
    )
    uploaded_by_name = models.CharField(max_length=200, editable=False)

    objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = pgettext_lazy("registrar.model.guest_document.meta", "guest roster document")
        verbose_name_plural = pgettext_lazy("registrar.model.guest_document.meta", "guest roster documents")
        indexes = [models.Index(fields=["organization", "enrollment", "-created_at"])]

    def save(self, *args, **kwargs):
        if self.uploaded_by_id and not self.uploaded_by_name:
            user = self.uploaded_by
            self.uploaded_by_name = ((user.get_full_name() or "").strip() or user.username)[:200]
        return super().save(*args, **kwargs)


__all__ = ["GUEST_DOCUMENT_EXTENSIONS", "GuestRosterDocument", "guest_document_path"]
