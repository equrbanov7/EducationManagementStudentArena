"""JSON / fayl uc nöqtələri — «Əmək müqavilələri» (HR) və «Müqavilələrim» (işçi).

Hamısı ``login_required`` + aktiv təşkilat; səlahiyyət servisdə (``services.contracts``) YAZIDAN ƏVVƏL yoxlanılır:
açar yoxdur → 403, əhatədən kənar → 404, view-as → 403. Cavab: ``{"ok": true, "message": …}`` və ya
``{"ok": false, "error": "<kod>", "message": …, "field": …}``.
"""

from __future__ import annotations

import functools

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from core.audit import log_action
from core.constants import AuditAction
from core.search_text import tolerant_q

from .constants import CTX, ContractStatus, ContractType
from .models import EmploymentContract
from .services import contracts as service
from .services.access import resolve_actor, staff_in_scope
from .services.errors import ContractError
from .services.notify import person_name

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
STAFF_PAGE_MAX = 30


def _error(exc: ContractError) -> JsonResponse:
    return JsonResponse({"ok": False, "error": exc.code, "message": exc.message, "field": exc.field}, status=exc.status)


def _no_org() -> JsonResponse:
    return JsonResponse(
        {"ok": False, "error": "no_organization", "message": pgettext(CTX, "Aktiv təşkilat konteksti yoxdur.")},
        status=403,
    )


def _guard(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if getattr(request, "organization", None) is None:
            return _no_org()
        try:
            return view(request, *args, **kwargs)
        except ContractError as exc:
            return _error(exc)

    return wrapper


@never_cache
@login_required
@require_POST
@_guard
def save(request):
    """Əlavə / redaktə / yeniləmə (multipart — fayl ola bilər)."""
    actor = resolve_actor(request)
    contract, created = service.save_contract(actor, request.POST, request.FILES, request=request)
    message = pgettext(CTX, "Müqavilə qeydə alındı.") if created else pgettext(CTX, "Dəyişikliklər yadda saxlanıldı.")
    return JsonResponse({"ok": True, "id": str(contract.pk), "created": created, "message": message})


@never_cache
@login_required
@require_POST
@_guard
def send(request, contract_id):
    actor = resolve_actor(request)
    service.mark_sent(actor, contract_id, note=request.POST.get("note", ""), request=request)
    return JsonResponse({"ok": True, "message": pgettext(CTX, "İşçiyə bildiriş göndərildi.")})


@never_cache
@login_required
@require_POST
@_guard
def terminate(request, contract_id):
    actor = resolve_actor(request)
    service.terminate(
        actor,
        contract_id,
        reason=request.POST.get("reason", ""),
        on=request.POST.get("terminated_at") or None,
        request=request,
    )
    return JsonResponse({"ok": True, "message": pgettext(CTX, "Müqaviləyə xitam verildi.")})


@never_cache
@login_required
@require_POST
@_guard
def discard(request, contract_id):
    """«Qaralamanı ləğv et» — yalnız qaralama (rəy A2)."""
    actor = resolve_actor(request)
    service.discard(actor, contract_id, note=request.POST.get("note", ""), request=request)
    return JsonResponse({"ok": True, "message": pgettext(CTX, "Qaralama ləğv edildi.")})


@never_cache
@login_required
@require_POST
@_guard
def acknowledge(request, contract_id):
    """İşçinin təsdiqi — açarsız, yalnız öz müqaviləsi (başqasınınkı → 404)."""
    service.acknowledge(
        request.user, request.organization, contract_id, note=request.POST.get("note", ""), request=request
    )
    return JsonResponse({"ok": True, "message": pgettext(CTX, "Təşəkkürlər — təsdiqiniz qeydə alındı.")})


def _field_labels() -> dict:
    return {
        "number": pgettext(CTX, "Müqavilə №"),
        "contract_type": pgettext(CTX, "Növ"),
        "position": pgettext(CTX, "Vəzifə"),
        "unit_id": pgettext(CTX, "Bölmə"),
        "start_date": pgettext(CTX, "Başlama tarixi"),
        "end_date": pgettext(CTX, "Bitmə tarixi"),
        "probation_end": pgettext(CTX, "Sınaq müddəti bitir"),
        "weekly_hours": pgettext(CTX, "Həftəlik saat"),
        "staff_rate": pgettext(CTX, "Ştat vahidi"),
        "notes": pgettext(CTX, "Qeyd"),
        "status": pgettext(CTX, "Vəziyyət"),
    }


def _display(key, value):
    if value in (None, ""):
        return ""
    if key == "contract_type" and value in ContractType.values:
        return ContractType(value).label
    if key == "status" and value in ContractStatus.values:
        return ContractStatus(value).label
    if key == "unit_id":
        from django.apps import apps as django_apps

        unit = django_apps.get_model("organizations", "OrgUnit").objects.filter(pk=value).values_list("name", flat=True)
        return next(iter(unit), value)
    return str(value)[:200]


@never_cache
@login_required
@require_GET
@_guard
def history(request, contract_id):
    """Hadisə tarixçəsi (HTML fraqment) — ``hr.contracts_view`` əhatəsində."""
    actor = resolve_actor(request)
    if not actor.can_view:
        raise ContractError("forbidden", pgettext(CTX, "Bu əməl üçün icazəniz yoxdur."), status=403)
    try:
        contract = EmploymentContract.objects.select_related("employee", "unit").get(
            organization=actor.organization, pk=contract_id
        )
    except service.LOOKUP_ERRORS:
        raise ContractError("not_found", pgettext(CTX, "Müqavilə tapılmadı."), status=404)
    if not actor.sees(contract):
        raise ContractError("not_found", pgettext(CTX, "Müqavilə tapılmadı."), status=404)
    labels = _field_labels()
    events = [
        {
            "event": event,
            "changes": [
                (labels.get(key, key), _display(key, pair[0]), _display(key, pair[1]))
                for key, pair in ((event.data or {}).get("changes") or {}).items()
            ],
        }
        for event in contract.events.select_related("actor").order_by("-created_at")[:200]
    ]
    html = render_to_string(
        "hr_contracts/cabinet/_history.html",
        {"contract": contract, "events": events, "employee_name": person_name(contract.employee)},
        request=request,
    )
    return JsonResponse({"ok": True, "html": html})


@never_cache
@login_required
@require_GET
@_guard
def staff(request):
    """İşçi seçicisi (``EMSSearchableSelect``) — yalnız idarə əhatəsindəki aktiv HEYƏT (tələbə yoxdur)."""
    actor = resolve_actor(request)
    if not actor.can_manage:
        raise ContractError("forbidden", pgettext(CTX, "Bu əməl üçün icazəniz yoxdur."), status=403)
    try:
        offset = max(0, int(request.GET.get("offset") or 0))
        limit = min(STAFF_PAGE_MAX, max(1, int(request.GET.get("limit") or 20)))
    except ValueError:
        offset, limit = 0, 20
    rows = staff_in_scope(actor.organization, actor.manage_scope).select_related("user", "role", "scope_unit")
    query = tolerant_q(
        request.GET.get("q", ""),
        fields=("user__first_name", "user__last_name", "user__username", "title"),
    )
    if query is not None:
        rows = rows.filter(query)
    rows = rows.order_by("user__last_name", "user__first_name", "user_id", "-is_primary")
    seen, results = set(), []
    for membership in rows[: (offset + limit) * 3 + 30]:
        if membership.user_id in seen:
            continue
        seen.add(membership.user_id)
        hint = " · ".join(part for part in (membership.title, getattr(membership.scope_unit, "name", "")) if part)
        results.append(
            {
                "id": str(membership.user_id),
                "text": person_name(membership.user),
                "label": person_name(membership.user),
                "meta": hint or membership.role.display_name,
            }
        )
    page = results[offset : offset + limit]
    return JsonResponse({"results": page, "has_more": len(results) > offset + limit})


@never_cache
@login_required
@require_GET
@_guard
def export(request):
    """Cari filtr dəstinin Excel ixracı — ``hr.contracts_view``; view-as-da bağlıdır; audit olunur."""
    from .services.export import xlsx_bytes
    from .services.panel import _units, parse_params
    from .services.queries import filtered

    actor = resolve_actor(request)
    if not actor.can_view:
        raise ContractError("forbidden", pgettext(CTX, "Bu əməl üçün icazəniz yoxdur."), status=403)
    if actor.view_as:
        raise ContractError("view_as_read_only", pgettext(CTX, "Baxış rejimində ixrac bağlıdır."), status=403)
    params = parse_params(request, _units(actor))
    rows, on, window = filtered(actor, params)
    rows = list(rows.order_by("end_date", "employee__last_name", "pk")[:5000])
    payload = xlsx_bytes(rows, on=on, window=window)
    log_action(
        AuditAction.EXPORT,
        user=request.user,
        organization=actor.organization,
        request=request,
        resource_type=service.AUDIT_RESOURCE,
        resource_repr=f"XLSX · {len(rows)}",
        reason=pgettext(CTX, "Əmək müqavilələri ixracı"),
        new_values={"format": "xlsx", "filters": params.as_query(), "rows": len(rows)},
    )
    response = HttpResponse(payload, content_type=_XLSX)
    response["Content-Disposition"] = (
        f'attachment; filename="emek-muqavileleri-{timezone.localdate().isoformat()}.xlsx"'
    )
    return response


__all__ = ["acknowledge", "discard", "export", "history", "save", "send", "staff", "terminate"]
