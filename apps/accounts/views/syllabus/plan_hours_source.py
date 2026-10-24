"""Sillabusun plan saatının MƏNBƏYİ (glue) + kafedranın əl ilə düzəlişi (sahib 2026-10-25).

Sillabusun plan saatı fənnin BİR QRUP üçün saatıdır (müəllimin ümumi yükü deyil):

1. kafedra / tədris şöbəsinin əl ilə düzəlişi — ``Syllabus.plan_hours_override``;
2. ``registrar.plan_hours_for_offering`` — qrupun ixtisas planı → yükdə bir qrupa düşən pay → istənilən plan.

``apps.syllabus`` registrar-ı idxal etmir, ona görə birləşdirən qat buradadır (accounts).
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from django.utils.translation import pgettext_lazy
from django.views.decorators.http import require_POST

from apps.syllabus.models import SyllabusVersion
from apps.syllabus.public import TransitionDenied, services

from .._helpers import _get_active_organization
from .labels import HOUR_KIND_LABELS, transition_text
from .lookup import safe_uuid

_CTX = "accounts.syllabus"
_KINDS = ("lecture", "seminar", "lab")

_NO_ORG = pgettext_lazy(_CTX, "Aktiv təşkilat seçilməyib.")
_NOT_FOUND = pgettext_lazy(_CTX, "Sillabus tapılmadı.")
_BAD_REQUEST = pgettext_lazy(_CTX, "Sorğu düzgün deyil.")
_EMPTY = pgettext_lazy(_CTX, "Ən azı bir dərs növü üçün saat seçin.")
_OVERRIDE_SAVED = pgettext_lazy(_CTX, "Plan saatı düzəldildi — %(count)s versiya yeniləndi.")
_OVERRIDE_RESET = pgettext_lazy(_CTX, "Əl ilə düzəliş silindi — saat yenidən tədris planı / dərs yükündən gəlir.")


def official_plan_hours(syllabus) -> dict:
    """Dosyenin RƏSMİ plan saatı: kafedranın düzəlişi, yoxdursa plan / yükdə bir qrupun payı."""
    if syllabus is None:
        return {}
    override = services.clean_override_hours(getattr(syllabus, "plan_hours_override", None))
    if override:
        return override
    from apps.registrar.public import plan_hours_for_offering

    return plan_hours_for_offering(getattr(syllabus, "offering", None)) or {}


def ensure_plan_hours(syllabus, context, *, write) -> tuple[dict, bool]:
    """Plan saatı + «müəllim əl ilə dəyişə bilərmi» bayrağı (``editor`` üçün).

    Sahib 2026-09-20: plan saatı boşdursa tədris yükündən doldurulur; rəsmi saat TAPILMAYANDA müəllim saatı
    özü seçir və (2026-09-25) redaktəyə açıq versiyada həmişə yenidən seçə bilir. Rəsmi saat (o cümlədən
    kafedranın düzəlişi) dəyişdirilmir. Audit 2026-09-28 SYL-7: yalnız MÜƏLLİFİN GET-i yazır (``write``);
    sahib 2026-10-12: rəsmi saat dəyişibsə müəllifin açıq qaralaması uyğunlaşır (təsdiqlənmişə yazılmır).
    """
    plan_hours = dict(context.get("plan_hours") or {})
    if context.get("view_state") != "normal":
        return plan_hours, False
    author = bool(context.get("is_author"))
    found = official_plan_hours(syllabus)
    if found:
        if dict(found) != plan_hours:
            if author:
                write(context["version"], found)
            return dict(found), False
        return plan_hours, False
    return plan_hours, author


def override_state(request, organization, syllabus, version, options) -> dict:
    """Redaktorun «Plan saatını düzəlt» forması üçün context (icazə yoxdursa ``{"allowed": False}``)."""
    actor = services.resolve_actor(getattr(request, "user", None), organization, request=request)
    if not services.can_override_plan_hours(actor, syllabus):
        return {"allowed": False}
    from apps.registrar.public import plan_hours_for_offering

    override = services.clean_override_hours(syllabus.plan_hours_override)
    auto = plan_hours_for_offering(getattr(syllabus, "offering", None)) or {}
    current = override or auto or dict(version.plan_hours or {})
    return {
        "allowed": True,
        "active": bool(override),
        "url": reverse("accounts:syllabus_plan_hours_override", args=[version.pk]),
        "auto": " · ".join(f"{HOUR_KIND_LABELS[kind]} {auto[kind]}" for kind in _KINDS if auto.get(kind)),
        "options": options,
        "fields": [
            {"kind": kind, "label": HOUR_KIND_LABELS[kind], "value": int(current.get(kind) or 0)} for kind in _KINDS
        ],
    }


def _hours_from(payload) -> dict | None:
    hours = {}
    for kind in _KINDS:
        try:
            hours[kind] = int(payload.get(kind) or 0)
        except (TypeError, ValueError):
            return None
        if hours[kind] < 0 or hours[kind] > services.plan_override.MAX_PLAN_HOURS:
            return None
    return hours


@login_required
@require_POST
def syllabus_plan_hours_override(request, version_id):
    """Kafedra / tədris şöbəsi: dosyenin plan saatını əl ilə düzəlt (``reset`` → avtomatik hesaba qayıt)."""
    organization = _get_active_organization(request)
    if organization is None:
        return JsonResponse({"ok": False, "error": str(_NO_ORG)}, status=403)
    parsed = safe_uuid(version_id)
    version = (
        SyllabusVersion.objects.filter(organization=organization, pk=parsed)
        .select_related("syllabus", "syllabus__offering")
        .first()
        if parsed
        else None
    )
    if version is None:
        return JsonResponse({"ok": False, "error": str(_NOT_FOUND)}, status=404)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": str(_BAD_REQUEST)}, status=400)
    reset = bool(payload.get("reset"))
    hours = {} if reset else _hours_from(payload)
    if hours is None:
        return JsonResponse({"ok": False, "error": str(_BAD_REQUEST)}, status=400)
    if not reset and not any(hours.values()):
        return JsonResponse({"ok": False, "error": str(_EMPTY)}, status=400)
    from apps.registrar.public import plan_hours_for_offering

    syllabus = version.syllabus
    actor = services.resolve_actor(request.user, organization, request=request)
    try:
        result = services.set_plan_hours_override(
            syllabus=syllabus,
            hours=hours,
            actor=actor,
            auto_hours=plan_hours_for_offering(syllabus.offering) if syllabus.offering_id else {},
            request=request,
        )
    except TransitionDenied as denied:
        return JsonResponse({"ok": False, "error": transition_text(denied.code), "code": denied.code}, status=403)
    message = _OVERRIDE_RESET if reset else str(_OVERRIDE_SAVED) % {"count": len(result["versions"])}
    return JsonResponse({"ok": True, "message": str(message), **result})


__all__ = ["ensure_plan_hours", "official_plan_hours", "override_state", "syllabus_plan_hours_override"]
