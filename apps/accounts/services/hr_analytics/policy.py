"""«Kadr analitikası» AKTOR qapısı (sahib 2026-10-11) — fail-closed.

Kim görür: `people.hr_analytics` açarını daşıyan rol (şablonda `hr`; `*` ilə rektor), RİM rəhbəri
(``ikt_rehber`` — sahibin «hər şeyi görsün» qərarı, açar daraldılsa belə) və superadmin / təşkilat
sahibi. Menyu qapısı ``views/_helpers/rbac_sections.py``-dadır; bu modul onu HƏR endpoint-də (panel,
ixrac) təkrarlayır. Əhatə: ORGANIZATION rolu → bütün təşkilat; açarı alan UNIT rolu → öz alt-ağacı;
əhatəsiz aktor → giriş YOX (boş vəziyyət, «bütün universitet» DEYİL).
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.organizations.public import EMPTY_SCOPE, ORG_WIDE_SCOPE, UnitScope, get_permission_scope
from core.permissions import has_permission

from ..people.permissions import PERM_VIEW_DEMOGRAPHICS
from .constants import PERM_HR_ANALYTICS


@dataclass(frozen=True)
class HrActor:
    user: object
    organization: object | None
    has_access: bool
    scope: UnitScope
    can_view_demographics: bool
    view_as: bool

    def unit_visible(self, unit_id, unit_path: str) -> bool:
        """Struktur vahidi aktorun əhatəsindədirmi (Python-da — əlavə sorğu yoxdur)."""
        if self.scope.is_org_wide:
            return True
        if not self.scope.is_unit_scoped or not unit_id:
            return False
        if str(unit_id) in {str(pk) for pk in self.scope.unit_ids}:
            return True
        return any((unit_path or "").startswith(f"{path}/") for path in self.scope.unit_paths)


_NOBODY = HrActor(
    user=None, organization=None, has_access=False, scope=EMPTY_SCOPE, can_view_demographics=False, view_as=False
)


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def resolve_actor(request) -> HrActor:
    """Sorğudan aktoru qurur; heç vaxt exception atmır."""
    from apps.accounts.views._helpers.rbac import _collect_actor_permissions
    from apps.accounts.views._helpers.rbac_sections import _is_rim_head
    from apps.accounts.views._helpers.tenant import _get_active_organization

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return _NOBODY
    organization = _get_active_organization(request)
    view_as = bool(getattr(request, "is_view_as", False))
    if organization is None:
        return HrActor(user, None, False, EMPTY_SCOPE, False, view_as)

    is_owner = getattr(organization, "owner_id", None) == getattr(user, "pk", None)
    if _is_superadmin(user) or is_owner or _is_rim_head(user, organization):
        return HrActor(user, organization, True, ORG_WIDE_SCOPE, True, view_as)

    permissions, _grantable = _collect_actor_permissions(user, organization)
    permissions = list(permissions)
    if not has_permission(permissions, PERM_HR_ANALYTICS):
        return HrActor(user, organization, False, EMPTY_SCOPE, False, view_as)
    scope = get_permission_scope(user, organization, PERM_HR_ANALYTICS, request=request)
    demographics = has_permission(permissions, PERM_VIEW_DEMOGRAPHICS)
    return HrActor(user, organization, scope.has_structure_access, scope, demographics, view_as)


__all__ = ["HrActor", "PERM_HR_ANALYTICS", "resolve_actor"]
