"""
organizations/views — FASAD (F5 rol-skeleti, 2026-07-02, AGENTS §6).

Köhnə views.py {member,org_admin,shared} paketlərinə bölünüb. urls.py və
accounts profil dashboard-unun lazy importları üçün səth dəyişmir.
"""

from .member import select_organization, switch_organization
from .org_admin import (
    build_organization_members_context,
    build_organization_roles_context,
    build_organization_structure_context,
    organization_dashboard,
    organization_members,
    organization_roles,
    organization_settings,
    organization_structure,
)

# structure_views/ paketi bu private helper-ləri tarixən buradan idxal edir
# (AGENTS §1: kənarda istifadə olunan underscore adlar fasadda saxlanmalıdır).
from .org_admin.context import _structure_ajax_response  # noqa: F401
from .shared._helpers import (  # noqa: F401
    _can_manage_organization,
    _can_view_structure,
    _get_structure_scope,
    _has_org_permission,
    _is_ajax_request,
    _unique_unit_slug,
    _visible_units_queryset,
)

__all__ = [
    "select_organization",
    "switch_organization",
    "organization_dashboard",
    "organization_structure",
    "organization_members",
    "organization_roles",
    "organization_settings",
    "build_organization_structure_context",
    "build_organization_members_context",
    "build_organization_roles_context",
]
