"""«Elan statistikası» (sahib 2026-11-18) — yalnız ``announcement.manage`` menecerləri.

Səhifənin özü YÜNGÜLDÜR (elan seçicisi + filtrlər, ağır sorğu yoxdur); bölgü və şəxs siyahısı
ayrı JSON uçlarından tənbəl (AJAX) yüklənir. Elan ``manage._load`` ilə açılır — əhatədən kənar
elan 404 verir (dekan yalnız öz elanlarının statistikasını görür). Baxış rejimində (view-as) giriş
yoxdur (``access.manage_scope`` boş əhatə qaytarır).
"""

from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.organizations.public import create_audit_log
from core.constants import AuditAction

from ..constants import STATS_DIMENSIONS, STATS_PICKER_LIMIT, STATS_STATUSES, Audience, Status
from ..models import Announcement
from ..services import access, stats
from ..services import stats_export as export_svc
from ..services import stats_units as units_svc
from ._base import error, ok
from .manage import _gate, _load, _page_context

_CTX = "announcements.stats"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _uuid(value) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return ""


def _params(request, organization, scope) -> dict:
    get = request.GET
    dimension = get.get("dim") or "faculty"
    family = get.get("role") or ""
    status = get.get("status") or "all"
    try:
        page = max(1, min(int(get.get("page") or 1), 10000))
    except (TypeError, ValueError):
        page = 1
    unit = units_svc.selected_option(scope, organization, _uuid(get.get("unit")))
    return {
        "elan": _uuid(get.get("elan")),
        "dim": dimension if dimension in STATS_DIMENSIONS else "faculty",
        "role": family if family in {value for value, _label in Audience.choices} else "",
        "unit": unit["id"] if unit else "",
        "unit_option": unit,
        "status": status if status in STATS_STATUSES else "all",
        "q": (get.get("q") or "").strip()[:100],
        "page": page,
    }


def _picker(organization, scope, user) -> list:
    rows = (
        Announcement.objects.filter(organization=organization, is_deleted=False)
        .exclude(status=Status.DRAFT)
        .filter(access.manageable_q(scope, user, organization))
        .order_by("-publish_at", "-created_at")
        .values("pk", "title", "publish_at")[:STATS_PICKER_LIMIT]
    )
    return [
        {
            "id": str(row["pk"]),
            "text": (
                f"{row['title']} · {timezone.localtime(row['publish_at']).strftime('%d.%m.%Y')}"
                if row["publish_at"]
                else row["title"]
            ),
        }
        for row in rows
    ]


def _json_gate(request):
    try:
        organization, scope = _gate(request)
    except PermissionDenied:
        return None
    params = _params(request, organization, scope)
    if not params["elan"]:
        return None
    announcement = _load(request, organization, scope, params["elan"])
    return organization, scope, params, announcement


@login_required
@require_GET
def stats_page(request):
    organization, scope = _gate(request)
    params = _params(request, organization, scope)
    picker = _picker(organization, scope, request.user)
    if not params["elan"] and picker:
        params["elan"] = picker[0]["id"]
    announcement = _load(request, organization, scope, params["elan"]) if params["elan"] else None
    if announcement is not None and all(item["id"] != str(announcement.pk) for item in picker):
        picker.insert(0, {"id": str(announcement.pk), "text": announcement.title})
    families = set(announcement.audience_families or ()) if announcement else set()
    unit_options = units_svc.initial_options(scope, organization)
    selected = params["unit_option"]
    if selected and all(item["id"] != selected["id"] for item in unit_options):
        unit_options.insert(0, selected)
    context = _page_context(
        request,
        embed_section_title=pgettext(_CTX, "Elan statistikası"),
        announcement=announcement,
        picker=picker,
        params=params,
        dimensions=[
            ("faculty", pgettext(_CTX, "Fakültə üzrə")),
            ("chair", pgettext(_CTX, "Kafedra üzrə")),
            ("specialty", pgettext(_CTX, "İxtisas üzrə")),
            ("group", pgettext(_CTX, "Qrup üzrə")),
            ("role", pgettext(_CTX, "Rol üzrə")),
        ],
        families=[(value, label) for value, label in Audience.choices if value in families],
        unit_options=unit_options,
    )
    return render(request, "announcements/manage/stats.html", context)


@never_cache
@login_required
@require_GET
def stats_summary(request):
    gate = _json_gate(request)
    if gate is None:
        return error(pgettext(_CTX, "Səlahiyyət yoxdur."), status=403)
    _organization, _scope, params, announcement = gate
    data = stats.summary(announcement, dimension=params["dim"], family=params["role"], unit=params["unit"])
    html = render_to_string(
        "announcements/manage/_stats_summary.html", {"data": data, "announcement": announcement}, request
    )
    return ok(html=html, totals=data["totals"])


@never_cache
@login_required
@require_GET
def stats_people(request):
    gate = _json_gate(request)
    if gate is None:
        return error(pgettext(_CTX, "Səlahiyyət yoxdur."), status=403)
    _organization, _scope, params, announcement = gate
    listing = stats.people_page(
        announcement,
        family=params["role"],
        unit=params["unit"],
        status=params["status"],
        q=params["q"],
        page=params["page"],
    )
    html = render_to_string(
        "announcements/manage/_stats_people.html", {"people": listing, "announcement": announcement}, request
    )
    return ok(html=html, total=listing["total"], page=listing["page"], pages=listing["pages"])


@never_cache
@login_required
@require_GET
def stats_units(request):
    """Bölmə filtrinin uzaq axtarışı — ``{"results": [{"id", "text"}]}``."""
    try:
        organization, scope = _gate(request)
    except PermissionDenied:
        return JsonResponse({"results": []}, status=403)
    query = (request.GET.get("q") or "").strip()[:100]
    return JsonResponse({"results": units_svc.search_units(scope, organization, query)})


@never_cache
@login_required
@require_GET
def stats_export(request):
    gate = _json_gate(request)
    if gate is None:
        raise PermissionDenied
    organization, _scope, params, announcement = gate
    payload, count = export_svc.xlsx_bytes(
        announcement,
        dimension=params["dim"],
        family=params["role"],
        unit=params["unit"],
        status=params["status"],
        q=params["q"],
    )
    create_audit_log(
        request.user,
        organization,
        AuditAction.EXPORT,
        resource_type="announcement",
        resource_id=str(announcement.pk),
        resource_repr=announcement.title[:200],
        new_values={"format": "xlsx", "rows": count, **{key: params[key] for key in ("dim", "role", "unit", "status")}},
        request=request,
    )
    stamp = timezone.localdate().strftime("%d.%m.%Y")
    response = HttpResponse(payload, content_type=_XLSX)
    response["Content-Disposition"] = f'attachment; filename="elan-statistikasi-{stamp}.xlsx"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


__all__ = ["stats_export", "stats_page", "stats_people", "stats_summary", "stats_units"]
