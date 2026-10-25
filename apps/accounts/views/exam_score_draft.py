"""«İmtahan balının daxil edilməsi» — QARALAMA (avtomatik saxlanma, sahib 2026-10-25).

Sahib: «səhifə yenilənsə də daxil edilən ballar itməsin (server-side qaralama — draft avtomatik saxlanma; ən azı
localStorage)». Qaralama SERVER keşindədir (Redis, ``CACHES["default"]``) — istifadəçi × açılış × imtahan növü
üzrə bir dəst, 14 gün yaşayır; brauzer eyni dəsti ``localStorage``-a da yazır (şəbəkə kəsiləndə ehtiyat).

* Qaralama RƏSMİ bal DEYİL: heç bir cədvələ yazmır, auditə düşmür, tələbə görmür. Sistemə yalnız
  «Yadda saxla» → təsdiq dialoqu yazır (``exam_score_entry`` view-u); uğurlu yazıdan sonra qaralama silinir.
* Qapı yazı ilə EYNİDİR: ``final_score.entry`` + açılış aktorun struktur əhatəsində (fail-closed); açar
  təşkilat + istifadəçi id-si ilə — başqasının qaralamasını oxumaq mümkün deyil.
* Ölçü həddi :data:`MAX_BYTES` (60 tələbə × 10 sütun ~ 10 KB) — böyük gövdə 413.

URL ``/accounts/imtahan-bali/qaralama/`` — ``/accounts/imtahan-bali/`` prefiksi ilə birlikdə yalnız daxili
şəbəkədə açıqdır (``network_zone.EXAM_SCORE_PREFIXES``).
"""

from __future__ import annotations

import json
from uuid import UUID

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.registrar.public import exam_score_entry as service

from ._helpers import _get_active_organization, _is_superadmin_user
from .exam_score_entry import ExamScoreEntryError, _can_manage, _offering_or_error

TTL_SECONDS = 14 * 24 * 3600
MAX_BYTES = 64 * 1024
_ASSESSMENTS = ("midterm", "final")


def cache_key(*, organization_id, user_id, offering_id, assessment) -> str:
    return f"ese-draft:v1:{organization_id}:{user_id}:{offering_id}:{assessment}"


def clear_draft(*, organization_id, user_id, offering_id, assessment) -> None:
    """Uğurlu yazıdan sonra (``exam_score_entry._handle_save``) qaralamanı sil."""
    cache.delete(
        cache_key(organization_id=organization_id, user_id=user_id, offering_id=offering_id, assessment=assessment)
    )


def _bad(message, status=400):
    return JsonResponse({"ok": False, "detail": message}, status=status)


def _resolve(request, organization, params):
    offering_id = str(params.get("offering") or "").strip()
    assessment = str(params.get("assessment") or "").strip()
    try:
        UUID(offering_id)
    except (TypeError, ValueError):
        return None, assessment
    if assessment not in _ASSESSMENTS:
        return None, assessment
    if _is_superadmin_user(request.user):  # superadmin təşkilatı ``ese_org`` ilə seçir (kökün `data-org`-u)
        organization = _superadmin_org(params.get("org")) or organization
    if organization is None:
        return None, assessment
    try:  # açılış həmin təşkilatındır (yazı view-u ilə eyni köməkçi)
        offering = _offering_or_error(request, organization, offering_id)
    except ExamScoreEntryError:
        return None, assessment
    if not _is_superadmin_user(request.user) and not service.offering_in_actor_scope(
        request.user, organization, offering
    ):
        return None, assessment
    return offering, assessment


def _superadmin_org(raw):
    from apps.organizations.models import Organization

    try:
        return Organization.objects.filter(pk=UUID(str(raw or ""))).first()
    except (TypeError, ValueError):
        return None


@login_required
@require_http_methods(["GET", "POST", "DELETE"])
def exam_score_draft(request):
    """GET — qaralamanı oxu; POST (JSON) — yaz; DELETE — sil. Cavab həmişə JSON."""
    organization = _get_active_organization(request)
    if not _can_manage(request.user, organization):
        return _bad("forbidden", status=403)
    if request.method == "POST":
        if len(request.body or b"") > MAX_BYTES:
            return _bad("too_large", status=413)
        try:
            body = json.loads(request.body or b"{}")
        except ValueError:  # UnicodeDecodeError ValueError-un alt sinfidir
            return _bad("invalid_json")
        if not isinstance(body, dict):
            return _bad("invalid_json")
        params = body
    else:
        params = request.GET
    offering, assessment = _resolve(request, organization, params)
    if offering is None:
        return _bad("not_found", status=404)
    key = cache_key(
        organization_id=offering.organization_id,
        user_id=request.user.pk,
        offering_id=offering.pk,
        assessment=assessment,
    )
    if request.method == "DELETE":
        cache.delete(key)
        return JsonResponse({"ok": True})
    if request.method == "POST":
        payload = body.get("payload")
        if not isinstance(payload, dict):
            return _bad("invalid_payload")
        saved_at = timezone.now().isoformat()
        cache.set(key, {"payload": payload, "saved_at": saved_at}, TTL_SECONDS)
        return JsonResponse({"ok": True, "saved_at": saved_at})
    stored = cache.get(key)
    if not isinstance(stored, dict):
        return JsonResponse({"ok": True, "draft": None})
    return JsonResponse({"ok": True, "draft": stored.get("payload"), "saved_at": stored.get("saved_at", "")})


__all__ = ["cache_key", "clear_draft", "exam_score_draft"]
