"""structure_views paketi — endpoints."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET

from core.constants import OrgUnitType

from ..models import Organization
from ..views import _can_view_structure, _get_structure_scope
from ._shared import (
    _get_visible_unit,
    _handle_faculty_action,
    _handle_kafedra_action,
    _structure_page_view,
)
from .constants import KAFEDRA_UNIT_TYPES
from .context import (
    build_organization_faculties_context,
    build_organization_kafedras_context,
)
from .unit_detail import build_unit_detail_context


@login_required
def organization_faculties(request, slug):
    """Fakültələrin idarə edilməsi (siyahı, yaratma, redaktə, silmə, dekan təyini)."""
    return _structure_page_view(
        request,
        slug,
        section_name="org-faculties",
        context_builder=build_organization_faculties_context,
        action_handler=_handle_faculty_action,
        partial_template="accounts/profile/sections/_org_faculties.html",
        context_key="org_faculties_section",
        page_template="organizations/faculties.html",
        redirect_url_name="organizations:structure_faculties",
    )


@login_required
def organization_kafedras(request, slug):
    """Kafedraların idarə edilməsi (siyahı, filtr, CRUD, müdir/müəllim təyinatı)."""
    return _structure_page_view(
        request,
        slug,
        section_name="org-kafedras",
        context_builder=build_organization_kafedras_context,
        action_handler=_handle_kafedra_action,
        partial_template="accounts/profile/sections/_org_kafedras.html",
        context_key="org_kafedras_section",
        page_template="organizations/kafedras.html",
        redirect_url_name="organizations:structure_kafedras",
    )


@login_required
@require_GET
def organization_unit_detail(request, slug, unit_id):
    """Fakültə/kafedra "ətraflı görünüş" modalı — AJAX-only JSON fraqment.

    Kart/sətir üzərinə klikdən çağırılır (bax ``static/js/org_structure.js``).
    Scope-təhlükəsizlik ``_get_visible_unit`` üzərindən keçir — redaktə/silmə
    formalarını qoruyan EYNİ funksiya: dekan yalnız öz fakültəsini, kafedra
    müdiri yalnız öz kafedrasını aça bilər (bax ``apps/organizations/scoping.py``,
    fail-closed ``EMPTY_SCOPE`` halı daxil olmaqla).
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    scope = _get_structure_scope(request, organization)
    if not _can_view_structure(request, organization, scope):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)

    unit = _get_visible_unit(organization, scope, str(unit_id), [OrgUnitType.FACULTY, *KAFEDRA_UNIT_TYPES])
    if unit is None:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)

    context = build_unit_detail_context(request, organization, scope, unit)
    html = render_to_string("organizations/partials/_unit_detail.html", context, request=request)
    return JsonResponse({"ok": True, "html": html, "unit_name": unit.name})
