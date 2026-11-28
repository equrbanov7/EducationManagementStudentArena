"""The university RİM head may configure journal-change notifications in their tenant."""

from core.constants import RoleScopeType
from core.permissions import has_permission

from .services import get_active_memberships


def has_journal_watch_access(user, organization, memberships=None):
    if not getattr(user, "is_active", False) or not organization or organization.org_type != "university":
        return False
    if not organization.is_active or organization.status != "active":
        return False
    if memberships is None:
        memberships = get_active_memberships(user, organization)
    return any(
        m.is_active
        and m.organization_id == organization.pk
        and m.role.organization_id == organization.pk
        and m.role.is_active
        and m.role.is_system
        and m.role.name == "ikt_rehber"
        and m.role.scope_type == RoleScopeType.ORGANIZATION
        and has_permission(m.role.permissions or [], "system.monitoring.view")
        for m in memberships
    )


def can_manage_journal_watch(request):
    return not getattr(request, "is_view_as", False) and has_journal_watch_access(
        request.user, getattr(request, "organization", None)
    )
