"""«Cədvəl idarəetməsi» bölməsinin JSON endpoint-ləri (`schedule.manage`).

Panel özü SERVER-RENDER-lidir (dövr/qrup seçimi fraqmenti yenidən yükləyir), ona
görə burada yalnız İKİ marşrut var:

* ``schedule_manage_check``  — SAXLAMADAN ƏVVƏL konflikt/validasiya yoxlaması;
  heç nə yazmır, konflikt slotunu (müəllim/otaq/qrup səbəbi ilə) qaytarır.
* ``schedule_manage_action`` — ``add`` / ``delete`` (allow-list); domen məntiqi
  ``apps.registrar.schedule_manage_actions``-dadır (audit + bildiriş orada).

Hər ikisi FAIL-CLOSED: icazəsi/əhatəsi olmayan aktor 403 alır. Açılışın MÜƏLLİMİ
olmaq səlahiyyət VERMİR — qapı yalnız ``schedule.manage`` açarındadır.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.registrar import schedule_manage as schedule_read
from apps.registrar import schedule_manage_actions as schedule_write
from apps.registrar.models import CourseOffering, ScheduleSlot

_CTX = "accounts.schedule_manage"

#: Naməlum `action` 400 verir (səssiz keçid yoxdur).
ALLOWED_ACTIONS = frozenset({"add", "delete"})


def _organization(request):
    from apps.accounts.views._helpers.tenant import _get_active_organization

    return _get_active_organization(request)


def _payload(request) -> dict:
    if "application/json" in (request.content_type or "").lower():
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
    return {key: value for key, value in request.POST.items()}


def _denied():
    return JsonResponse(
        {
            "ok": False,
            "error": "permission_denied",
            "message": pgettext(_CTX, "Dərs cədvəlini idarə etmək üçün icazəniz yoxdur."),
        },
        status=403,
    )


def _offering(request, organization, data):
    """Açılışı aktiv tenantda tap və aktorun əhatəsinə görə yoxla."""
    offering = (
        CourseOffering.objects.filter(pk=str(data.get("offering_id") or "").strip(), organization=organization)
        .select_related("organization", "subject", "group", "period", "instructor")
        .first()
    )
    if offering is None:
        return None
    if not schedule_read.can_manage_offering(request.user, organization, offering):
        return None
    return offering


@never_cache
@login_required
@require_POST
def schedule_manage_check(request):
    """Saxlama-öncəsi yoxlama — heç nə yazmır, konflikti göstərir."""
    organization = _organization(request)
    if organization is None or not schedule_read.can_manage(request.user, organization):
        return _denied()

    data = _payload(request)
    offering = _offering(request, organization, data)
    if offering is None:
        return _denied()

    cleaned, errors = schedule_read.parse_payload(data)
    if not errors:
        errors = schedule_read.check_slot(
            offering=offering,
            cleaned=cleaned,
            exclude_id=str(data.get("slot_id") or "").strip() or None,
        )
    conflict = errors.pop("_conflict", None)
    return JsonResponse({"ok": not errors, "errors": errors, "conflict": conflict})


@never_cache
@login_required
@require_POST
def schedule_manage_action(request):
    """Slot əlavəsi / silinməsi — vahid giriş nöqtəsi (allow-list)."""
    organization = _organization(request)
    if organization is None or not schedule_read.can_manage(request.user, organization):
        return _denied()

    data = _payload(request)
    action = str(data.get("action") or "").strip()
    if action not in ALLOWED_ACTIONS:
        return JsonResponse(
            {"ok": False, "error": "unknown_action", "message": pgettext(_CTX, "Naməlum əməliyyat.")},
            status=400,
        )

    try:
        if action == "add":
            offering = _offering(request, organization, data)
            if offering is None:
                return _denied()
            row = schedule_write.create_slot(
                actor=request.user,
                organization=organization,
                offering=offering,
                data=data,
                request=request,
            )
        else:
            slot = (
                ScheduleSlot.objects.filter(pk=str(data.get("slot_id") or "").strip(), organization=organization)
                .select_related("offering", "offering__organization", "offering__subject", "offering__group")
                .first()
            )
            if slot is None:
                return _denied()
            row = schedule_write.delete_slot(actor=request.user, organization=organization, slot=slot, request=request)
    except schedule_write.ScheduleManageError as exc:
        conflict = exc.errors.pop("conflict_slot", None)
        payload = {"ok": False, "error": exc.code, "message": exc.message, "errors": exc.errors}
        if conflict:
            payload["conflict"] = conflict
        return JsonResponse(payload, status=exc.status)

    return JsonResponse({"ok": True, "slot": row})


__all__ = ["ALLOWED_ACTIONS", "schedule_manage_action", "schedule_manage_check"]
