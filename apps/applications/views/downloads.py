"""İcazə qapılı sənəd yükləmə.

BOŞLUQ BAĞLANIR (scout §3): repo-da müraciət faylları üçün icazə yoxlayan
serve view yox idi; ``FileField.url`` faylı bilən hər kəsə açıq edir. Burada
fayl YALNIZ ``can_view`` keçən istifadəçiyə verilir və həmişə ƏLAVƏ kimi
(``Content-Disposition: attachment``) göndərilir ki, brauzer HTML/SVG-ni
mənbənin öz origin-ində icra etməsin.
"""

from __future__ import annotations

from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET

from ..models import ApplicationAttachment
from ._base import json_endpoint, load_application


@require_GET
@json_endpoint
def attachment_download(request, application_id, attachment_id, *, organization):
    application = load_application(request, organization, application_id)
    if application is None:
        raise Http404

    attachment = ApplicationAttachment.objects.filter(
        organization=organization, application=application, pk=attachment_id
    ).first()
    if attachment is None or not attachment.file:
        raise Http404

    try:
        handle = attachment.file.open("rb")
    except OSError as exc:  # pragma: no cover — itmiş fayl
        raise Http404 from exc

    response = FileResponse(handle, as_attachment=True, filename=attachment.original_name)
    response["Content-Type"] = attachment.content_type or "application/octet-stream"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


__all__ = ["attachment_download"]
