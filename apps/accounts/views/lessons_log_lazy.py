"""«Keçilmiş dərslər» — tənbəl AJAX ucları (PERF 2026-11-11, sahib: «girəndə bir az yavaşlama olur»).

Bölmənin ilk cavabı ağır hesabı gözləmir (`_sections.lessons_log`); iki uc qalanı gətirir:

* :func:`lessons_log_insights` — iştirak / boş / gec KPI-ları (xana cədvəli üzərində aqreqat) və «Cədvəldə var,
  qeydə alınmayıb» kartı (slot × tarix tutuşdurması). Nəticələr 300 s keşlənir — sonrakı açılış bölmənin öz
  cavabında hazır gəlir.
* :func:`lessons_log_rows` — gün siyahısının növbəti səhifəsi (`ll_offset`; gün başlığı günün TAM cəmidir).

Əhatə bölmə ilə EYNİDİR: hər iki uc `lessons_log.resolve_request`-dən keçir (müəllim yalnız öz dərsləri,
nəzarətçi öz alt-ağacı, əhatəsiz aktor — boş nəticə). Yazı yoxdur (GET, oxu-only).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.registrar.public import lessons_log as service
from core.tenancy import get_request_organization, request_has_active_organization_context

from .profile._sections.lessons_log import _group_by_day, _kpi_tiles


def _organization(request):
    organization = get_request_organization(request)
    if organization is None or not request_has_active_organization_context(request):
        return None
    return organization


def _denied() -> JsonResponse:
    return JsonResponse({"ok": False, "error": "no_active_organization"}, status=403)


@never_cache
@login_required
@require_GET
def lessons_log_insights(request):
    organization = _organization(request)
    if organization is None:
        return _denied()
    ctx = service.resolve_request(request, organization, with_options=False)
    totals = service.range_totals(ctx["lessons"])
    unrecorded = service.unrecorded_for(request, organization, ctx)
    tiles = [{key: str(tile[key]) for key in ("key", "value", "unit", "note", "tone")} for tile in _kpi_tiles(totals)]
    html = render_to_string(
        "accounts/profile/sections/_lessons_log_unrecorded.html",
        {"un": unrecorded, "is_supervisor": ctx["supervisor"]},
        request=request,
    )
    return JsonResponse({"ok": True, "kpi": tiles, "unrecorded_html": html})


@never_cache
@login_required
@require_GET
def lessons_log_rows(request):
    organization = _organization(request)
    if organization is None:
        return _denied()
    ctx = service.resolve_request(request, organization, with_options=False)
    page = service.page_rows(ctx["lessons"], offset=service.parse_offset(request.GET.get("ll_offset")))
    rows = page["rows"]
    count = len(rows)
    if ctx["only_flagged"]:
        rows = [row for row in rows if row["note"] != service.NOTE_ON_TIME]
    html = render_to_string(
        "accounts/profile/sections/_lessons_log_days.html",
        {"days": _group_by_day(rows, page["day_totals"]), "is_supervisor": ctx["supervisor"]},
        request=request,
    )
    return JsonResponse({"ok": True, "html": html, "next_offset": page["next_offset"], "count": count})


__all__ = ["lessons_log_insights", "lessons_log_rows"]
