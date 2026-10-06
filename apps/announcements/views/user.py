"""İstifadəçi səthi: siyahı fraqmenti (axtarış/filtr), oxundu, popup bağlandı, «Müraciət et», sənəd.

Ekranın özü kabinet bölməsidir (``?section=announcements``); bu uclar yalnız JSON/fayl verir.
Hər uc görünüş qapısını YENİDƏN tətbiq edir (auditoriya + təşkilat) — tapılmayan və
görünməyən elan eyni 404 cavabını alır (mövcudluq faktı sızmır).
"""

from __future__ import annotations

import uuid

from django.http import FileResponse, Http404, HttpResponseRedirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from ..constants import PROFILE_SECTION
from ..models import AnnouncementAttachment
from ..services import access, apply as apply_service, popup, queries
from ..services.audience import viewer_for
from ._base import error, json_body, member_endpoint, ok

_CTX = "announcements.api"


def _viewer(request):
    return viewer_for(request.user, request.organization, getattr(request, "org_memberships", None))


def _visible_or_404(request, announcement_id):
    announcement = queries.get_visible(request.organization, _viewer(request), announcement_id)
    if announcement is None:
        raise Http404
    return announcement


@never_cache
@require_GET
@member_endpoint
def list_fragment(request):
    params = queries.ListParams.from_query(request.GET)
    result = queries.user_list(request.organization, request.user, _viewer(request), params)
    html = render_to_string(
        "announcements/cabinet/_list.html", {"listing": result, "profile_base_url": reverse("accounts:profile")}, request
    )
    return ok(html=html, total=result["total"], page=result["page"], pages=result["pages"])


@require_POST
@member_endpoint
def mark_read(request, announcement_id):
    if getattr(request, "is_view_as", False):
        return ok(recorded=False)
    announcement = _visible_or_404(request, announcement_id)
    popup.mark_read(request, announcement)
    return ok(recorded=True)


@require_POST
@member_endpoint
def popup_seen(request):
    if getattr(request, "is_view_as", False):
        return ok(recorded=0)
    raw = json_body(request).get("ids") or []
    ids = []
    for item in raw if isinstance(raw, list) else []:
        try:
            ids.append(uuid.UUID(str(item)))
        except (TypeError, ValueError, AttributeError):
            continue
    if not ids:
        return error(pgettext(_CTX, "Elan seçilməyib."))
    return ok(recorded=popup.mark_popup_seen(request, ids))


@require_POST
@member_endpoint
def apply(request, announcement_id):
    announcement = _visible_or_404(request, announcement_id)
    note = str(json_body(request).get("note") or "")
    result = apply_service.apply(request, announcement, note)
    if not result.ok:
        return error(result.error, status=409)
    return ok(created=result.created, number=result.number, redirect=result.redirect)


@never_cache
@require_GET
@member_endpoint
def attachment_download(request, announcement_id, attachment_id):
    """Sənəd YALNIZ elanı görən istifadəçiyə (və ya onu idarə edə bilən menecerə), həmişə əlavə kimi."""
    organization = request.organization
    attachment = (
        AnnouncementAttachment.objects.filter(
            organization=organization, announcement_id=announcement_id, pk=attachment_id
        )
        .select_related("announcement")
        .first()
    )
    if attachment is None or not attachment.file:
        raise Http404
    visible = queries.get_visible(organization, _viewer(request), announcement_id) is not None
    if not visible:
        scope = access.manage_scope(request.user, organization, request=request)
        if not access.can_edit(scope, request.user, attachment.announcement, organization):
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


@require_GET
def detail_redirect(request, announcement_id):
    """Paylaşıla bilən qısa link → kabinetdəki detal (giriş/görünüş qapısı orada)."""
    return HttpResponseRedirect(f"{reverse('accounts:profile')}?section={PROFILE_SECTION}&elan={announcement_id}")


__all__ = ["apply", "attachment_download", "detail_redirect", "list_fragment", "mark_read", "popup_seen"]
