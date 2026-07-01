"""structure_views paketi — endpoints."""

from django.contrib.auth.decorators import login_required

from ._shared import (
    _handle_faculty_action,
    _handle_kafedra_action,
    _structure_page_view,
)
from .context import (
    build_organization_faculties_context,
    build_organization_kafedras_context,
)


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
