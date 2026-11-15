"""«Tələbəni bərpa et» — HTTP səthi (JSON GET siyahı + JSON POST bərpa, CSRF; sahib 2026-11-15).

Zəncir (fail-closed): tenant (``offering_or_404``) → açar (``journal.correct`` org-wide və ya əhatəli
``journal.roster``; heç biri yoxdursa **403**) → əhatə (açılış aktorun alt-ağacında deyilsə **404**) → servis
(:mod:`apps.registrar.journal_roster_restore`: siyahı qapısı **409**, növ açarı **403**, başqa jurnalda aktiv
**409**). Siyahı modal açılanda oxunur — səhifə yüklənəndə yalnız sayğac sorğusu var.
"""

from __future__ import annotations

import json
import uuid

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from . import journal_roster_restore as service
from . import subject_exempt
from .journal_access import offering_or_404

_CTX = "registrar.roster_restore"


def _error(code, message, status=400):
    return JsonResponse({"ok": False, "error": code, "message": str(message)}, status=status)


def _payload(request) -> dict:
    if "application/json" in (request.content_type or "").lower():
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}
    return {key: request.POST.get(key) for key in request.POST}


def _uuid(value):
    try:
        return uuid.UUID(str(value or "").strip())
    except (TypeError, ValueError, AttributeError):
        return None


def _guard(request, offering_id):
    """``(offering, None)`` və ya ``(None, JsonResponse)`` — 403 açarsız, 404 əhatədən kənar."""
    offering = offering_or_404(request, offering_id)
    if not subject_exempt.has_any_power(request.user, offering.organization):
        message = pgettext(_CTX, "Tələbəni jurnala bərpa etmək üçün səlahiyyətiniz yoxdur.")
        return None, _error("permission_denied", message, status=403)
    if not service.can_view(request.user, offering):
        raise Http404
    return offering, None


@never_cache
@login_required
@require_GET
def roster_restore_list(request, offering_id):
    offering, denied = _guard(request, offering_id)
    if denied is not None:
        return denied
    return JsonResponse(
        {
            "ok": True,
            "blocked": service.block_reason(offering),
            "rows": service.rows(request.user, offering),
        }
    )


@never_cache
@login_required
@require_POST
def roster_restore_apply(request, offering_id):
    offering, denied = _guard(request, offering_id)
    if denied is not None:
        return denied
    data = _payload(request)
    enrollment_id = _uuid(data.get("enrollment"))
    if enrollment_id is None:
        return _error("not_found", pgettext(_CTX, "Qeydiyyat tapılmadı."), status=404)
    try:
        result = service.restore(
            offering=offering,
            enrollment_id=enrollment_id,
            actor=request.user,
            note=data.get("note") or "",
            request=request,
        )
    except service.RestoreError as exc:
        return _error(exc.code, exc.message, status=exc.status)
    message = pgettext(_CTX, "Tələbə jurnala qaytarıldı — əvvəlki balları və davamiyyəti yerindədir.")
    return JsonResponse({"ok": True, "message": message, **result})


__all__ = ["roster_restore_apply", "roster_restore_list"]
