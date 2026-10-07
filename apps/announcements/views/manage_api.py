"""İdarə formasının JSON köməkçiləri (yalnız ``announcement.manage`` menecerləri).

* ``manage_audience_count`` — auditoriya seçicisinin altındakı canlı xülasə: «Kim görəcək: … —
  təxminən N nəfər» (debounce-lu GET). Bölmələr menecerin ƏHATƏSİ ilə yoxlanılır
  (``access.validate_units``); say ``services/recipients`` ilə bir ``COUNT`` sorğusudur.
* ``manage_recipients`` — məcburi elanın «təsdiq edənlər / gözləyənlər» siyahısı (axtarış + səhifə).

Hər ikisi təşkilat kontekstinə bağlıdır (``organization_id`` açıq süzülür + RLS).
"""

from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.template.loader import render_to_string
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from ..constants import MAX_TARGET_UNITS
from ..services import access, recipients
from ..services.audience import normalize_families
from ._base import error, ok
from .manage import _gate, _load

_CTX = "announcements.manage"


def _gate_json(request):
    try:
        return _gate(request)
    except PermissionDenied:
        return None


def _unit_ids(values) -> list:
    result = []
    for value in values:
        try:
            result.append(str(uuid.UUID(str(value))))
        except (TypeError, ValueError, AttributeError):
            continue
    return list(dict.fromkeys(result))[:MAX_TARGET_UNITS]


@never_cache
@login_required
@require_GET
def manage_audience_count(request):
    gate = _gate_json(request)
    if gate is None:
        return error(pgettext(_CTX, "Səlahiyyət yoxdur."), status=403)
    organization, scope = gate
    families = normalize_families(request.GET.getlist("families"))
    if not families:
        return ok(count=None, warning=True, text=pgettext(_CTX, "Kim görəcək: əvvəlcə auditoriyanı seçin."))
    units, errors = access.validate_units(scope, organization, _unit_ids(request.GET.getlist("units")))
    if errors:
        return ok(count=None, warning=True, text=errors[0])
    names = access.unit_rows(organization, units)
    count = recipients.audience_count(organization, families, units)
    text = recipients.summary_text(families, [names[pk][0] for pk in units if pk in names], count)
    return ok(count=count, warning=False, text=text)


@never_cache
@login_required
@require_GET
def manage_recipients(request, announcement_id):
    gate = _gate_json(request)
    if gate is None:
        return error(pgettext(_CTX, "Səlahiyyət yoxdur."), status=403)
    organization, scope = gate
    announcement = _load(request, organization, scope, announcement_id)
    if not announcement.requires_ack:
        raise Http404
    try:
        page = max(1, min(int(request.GET.get("page") or 1), 10000))
    except (TypeError, ValueError):
        page = 1
    listing = recipients.recipient_page(
        announcement, status=request.GET.get("status") or "pending", q=request.GET.get("q") or "", page=page
    )
    html = render_to_string("announcements/manage/_recipients.html", {"ack_page": listing}, request)
    return ok(html=html, total=listing["total"], page=listing["page"], pages=listing["pages"])


__all__ = ["manage_audience_count", "manage_recipients"]
