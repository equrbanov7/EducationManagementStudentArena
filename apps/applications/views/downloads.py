"""İcazə qapılı sənəd yükləmə.

BOŞLUQ BAĞLANIR (scout §3): repo-da müraciət faylları üçün icazə yoxlayan
serve view yox idi; ``FileField.url`` faylı bilən hər kəsə açıq edir. Burada
fayl YALNIZ ``can_view`` keçən istifadəçiyə verilir və həmişə ƏLAVƏ kimi
(``Content-Disposition: attachment``) göndərilir ki, brauzer HTML/SVG-ni
mənbənin öz origin-ində icra etməsin. ``Content-Type`` klientin yükləmədə
bəyan etdiyi dəyərdən yox, fayl adının uzantısından (ağ siyahı) çıxarılır.
"""

from __future__ import annotations

from django.http import Http404
from django.views.decorators.http import require_GET

from core.download_types import attachment_file_response

from ..models import ApplicationAttachment
from ..services import access
from ._base import json_endpoint, load_application


@require_GET
@json_endpoint
def attachment_download(request, application_id, attachment_id, *, organization):
    application = load_application(request, organization, application_id)
    if application is None:
        raise Http404

    attachment = (
        ApplicationAttachment.objects.filter(organization=organization, application=application, pk=attachment_id)
        .select_related("event")
        .first()
    )
    if attachment is None or not attachment.file:
        raise Http404
    attachment.application = application  # artıq yüklənib və görünüş yoxlanıb
    if not access.can_view_attachment(request.user, attachment):  # SEC-04: daxili qeydin sənədi
        raise Http404

    # Audit 2026-10-07: tip saxlanmış (klientin bəyan etdiyi) ``content_type``-dan YOX,
    # adın uzantısından (``core.download_types`` ağ siyahısı).
    return attachment_file_response(attachment.file, filename=attachment.original_name)


__all__ = ["attachment_download"]
