"""organizations modulunun PUBLIC API fasadı (M3-B, 2026-07-02).

Tenant/üzvlük/rol sorğuları üçün kanonik giriş nöqtəsi (AGENTS §5).
Permission-string uyğunlaşdırması core.permissions-dadır (has_permission);
burada yalnız org-domain xidmətləri təqdim olunur.
"""

from apps.organizations.permissions import (  # noqa: F401
    PERMISSION_CATEGORIES,
    get_all_permissions,
    is_grant_entry,
    strip_grant_prefix,
)
from apps.organizations.scoping import (  # noqa: F401
    get_unit_scope,
    scope_memberships_by_unit,
)
from apps.organizations.services import (  # noqa: F401
    create_audit_log,
    ensure_owner_membership,
    get_active_memberships,
    get_user_org_role_level,
    is_tenant_accessible_organization,
    organization_role_user_queryset,
    organization_user_queryset,
    user_has_org_role,
)
from apps.organizations.structure_views import (  # noqa: F401
    build_organization_faculties_context,
    build_organization_kafedras_context,
)
from apps.organizations.views import (  # noqa: F401
    build_organization_members_context,
    build_organization_roles_context,
    build_organization_structure_context,
)

__all__ = [
    "PERMISSION_CATEGORIES",
    "build_organization_faculties_context",
    "build_organization_kafedras_context",
    "build_organization_members_context",
    "build_organization_roles_context",
    "build_organization_structure_context",
    "create_audit_log",
    "ensure_owner_membership",
    "get_active_memberships",
    "get_all_permissions",
    "get_unit_scope",
    "get_user_org_role_level",
    "is_grant_entry",
    "is_tenant_accessible_organization",
    "organization_role_user_queryset",
    "organization_user_queryset",
    "scope_memberships_by_unit",
    "strip_grant_prefix",
    "user_has_org_role",
]
