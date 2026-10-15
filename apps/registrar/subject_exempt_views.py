"""«Fəndən azad et» / «Bərpa et» — HTTP səthi (JSON POST, CSRF; sahib 2026-10-15).

Zəncir (fail-closed): tenant (``offering_or_404``) → açar (``journal.correct`` org-wide və ya
``journal.roster``; heç biri yoxdursa **403**) → əhatə (açılışın qrupu aktorun alt-ağacında deyilsə **404**,
mövcudluq sızmasın) → siyahı qapısı (bağlı jurnal / keçmiş dövr → **409** + səbəb) → servis.
Domen məntiqi :mod:`apps.registrar.subject_exempt`-dədir.
"""

from __future__ import annotations

import json
import uuid

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from . import subject_exempt
from .journal_access import offering_or_404

_CTX = "registrar.subject_exempt"


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
    """``(offering, None)`` və ya ``(None, JsonResponse)`` — 403 açarsız, 404 əhatədən kənar, 409 bağlı."""
    offering = offering_or_404(request, offering_id)
    if not subject_exempt.has_any_power(request.user, offering.organization):
        message = pgettext(_CTX, "Tələbəni fəndən azad etmək üçün səlahiyyətiniz yoxdur.")
        return None, _error("permission_denied", message, status=403)
    if not subject_exempt.can_exempt(request.user, offering):
        raise Http404
    blocked = subject_exempt.block_reason(offering)
    if blocked:
        return None, _error("roster_closed", blocked, status=409)
    return offering, None


@never_cache
@login_required
@require_POST
def subject_exempt_apply(request, offering_id):
    offering, denied = _guard(request, offering_id)
    if denied is not None:
        return denied
    data = _payload(request)
    enrollment_id = _uuid(data.get("enrollment"))
    if enrollment_id is None:
        return _error("not_found", pgettext(_CTX, "Qeydiyyat tapılmadı."), status=404)
    try:
        result = subject_exempt.exempt_student(
            offering=offering,
            enrollment_id=enrollment_id,
            actor=request.user,
            reason=data.get("reason") or "",
            doc_number=data.get("doc_number") or "",
            doc_date=data.get("doc_date") or "",
            request=request,
        )
    except subject_exempt.HygieneError as exc:
        return _error(exc.code, exc.message, status=exc.status)
    message = pgettext(_CTX, "Tələbə bu fəndən azad edildi — qrupda qalır, digər fənlərə toxunulmadı.")
    return JsonResponse({"ok": True, "message": message, **result})


@never_cache
@login_required
@require_POST
def subject_exempt_restore(request, offering_id):
    offering, denied = _guard(request, offering_id)
    if denied is not None:
        return denied
    data = _payload(request)
    decision_id = _uuid(data.get("decision"))
    if decision_id is None:
        return _error("not_revertable", pgettext(_CTX, "Qərar tapılmadı və ya artıq geri qaytarılıb."), status=404)
    try:
        result = subject_exempt.restore_student(
            offering=offering,
            decision_id=decision_id,
            actor=request.user,
            reason=data.get("reason") or "",
            request=request,
        )
    except subject_exempt.HygieneError as exc:
        return _error(exc.code, exc.message, status=exc.status)
    return JsonResponse({"ok": True, "message": pgettext(_CTX, "Tələbə jurnala qaytarıldı."), **result})


__all__ = ["subject_exempt_apply", "subject_exempt_restore"]
