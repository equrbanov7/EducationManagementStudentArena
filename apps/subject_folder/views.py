"""Fayl endirmə endpoint-ləri — İCAZƏ QAPILI (ekranlar UI agentinin profil bölmələridir).

Hər endpoint obyekti AKTİV təşkilat kontekstində yükləyir (tenant sərhədi RLS-ə
tək qalmır), icazəni servis qatından yoxlayır və faylı ƏLAVƏ kimi verir
(``nosniff``, ``private, no-store``). İcazəsiz aktor 403 DEYİL, 404 alır —
faylın mövcudluğu bildirilmir.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.views.decorators.http import require_GET

from core.tenancy import get_request_organization, request_has_active_organization_context

from .models import FolderMaterial, SubmissionFile, TaskAttachment
from .services import access
from .services.media import file_response


def _organization(request):
    organization = get_request_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        raise Http404
    return organization


@login_required
@require_GET
def material_download(request, material_id):
    organization = _organization(request)
    material = (
        FolderMaterial.objects.filter(organization=organization, pk=material_id)
        .select_related("folder", "folder__organization", "topic")
        .first()
    )
    if material is None or not material.file or not access.can_view_material(request.user, material):
        raise Http404
    return file_response(material.file, filename=material.original_name, content_type=material.content_type)


@login_required
@require_GET
def task_attachment_download(request, attachment_id):
    organization = _organization(request)
    attachment = (
        TaskAttachment.objects.filter(organization=organization, pk=attachment_id)
        .select_related("task", "task__folder", "task__folder__organization", "task__topic")
        .first()
    )
    if attachment is None or not access.can_view_task(request.user, attachment.task):
        raise Http404
    return file_response(attachment.file, filename=attachment.original_name, content_type=attachment.content_type)


@login_required
@require_GET
def submission_file_download(request, file_id):
    organization = _organization(request)
    row = (
        SubmissionFile.objects.filter(organization=organization, pk=file_id)
        .select_related(
            "submission",
            "submission__assignment",
            "submission__assignment__folder",
            "submission__assignment__folder__organization",
            "submission__assignment__offering",
            "submission__assignment__offering__organization",
        )
        .first()
    )
    if row is None or not access.can_view_submission(request.user, row.submission):
        raise Http404
    return file_response(row.file, filename=row.original_name, content_type=row.content_type)


__all__ = ["material_download", "submission_file_download", "task_attachment_download"]
