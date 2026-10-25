"""Test köməkçisi: «alt qrupdan əlavə» qeydiyyatına sənəd bağla (nişan yalnız sənədli yerləşdirməyə — 2026-10-25)."""

from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.registrar.models import GuestRosterDocument
from core.rls import bypass_rls

PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def attach_guest_document(enrollment, user=None):
    """*enrollment* üçün təqdimat sənədi (modalın yazdığı kimi) — qaytarır: :class:`GuestRosterDocument`."""
    with bypass_rls():
        return GuestRosterDocument.objects.create(
            organization_id=enrollment.organization_id,
            enrollment=enrollment,
            document=SimpleUploadedFile("teqdimat.pdf", PDF_BYTES, content_type="application/pdf"),
            uploaded_by=user,
        )
