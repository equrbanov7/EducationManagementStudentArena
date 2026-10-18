"""Kim görür, kim idarə edir — FAIL-CLOSED.

* ``hr.contracts_view`` — siyahı, fayl, tarixçə, ixrac (OXU); ``hr.contracts_manage`` — əlavə, redaktə,
  yeniləmə, «göndərildi», xitam (idarə açarı oxunu da nəzərdə tutur).
* Əhatə ``organizations.scoping.get_permission_scope``-dan: ORGANIZATION rolu / sahib / superadmin → bütün
  təşkilat; açarı alan UNIT rolu → yalnız ``scope_unit`` alt-ağacı (müqavilənin ``unit``-i həmin ağacda
  olmalıdır; bölməsiz müqaviləni yalnız təşkilat səviyyəli aktor görür).
* «Başqasının adından» (view-as) rejimində HEÇ BİR yazı yoxdur — idarə əhatəsi boşalır.
* İşçinin öz müqavilələri (``Müqavilələrim``) açarsızdır: yalnız ``employee == user`` və qaralama olmayan.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.apps import apps as django_apps
from django.db.models import Q

from apps.organizations.public import EMPTY_SCOPE, ORG_WIDE_SCOPE, UnitScope, get_permission_scope

from ..constants import NON_EMPLOYEE_ROLE_NAMES, PERM_MANAGE, PERM_VIEW


def _merge(first: UnitScope, second: UnitScope) -> UnitScope:
    if first.is_org_wide or second.is_org_wide:
        return ORG_WIDE_SCOPE
    ids = frozenset(first.unit_ids) | frozenset(second.unit_ids)
    paths = tuple(dict.fromkeys(tuple(first.unit_paths) + tuple(second.unit_paths)))
    if not ids and not paths:
        return EMPTY_SCOPE
    return UnitScope(scope_type="unit", unit_ids=ids, unit_paths=paths)


def unit_in_scope(scope: UnitScope, unit_id, unit_path: str) -> bool:
    if scope.is_org_wide:
        return True
    if not scope.is_unit_scoped or not unit_id:
        return False
    if str(unit_id) in {str(pk) for pk in scope.unit_ids}:
        return True
    return any((unit_path or "").startswith(f"{path}/") for path in scope.unit_paths)


def contracts_q(scope: UnitScope) -> Q:
    """Müqavilə queryset-i üçün əhatə filtri (bölməsiz müqavilə yalnız org-wide əhatədə)."""
    if scope.is_org_wide:
        return Q()
    if not scope.is_unit_scoped:
        return Q(pk__in=[])
    return scope.unit_subtree_q(path_field="unit__path", id_field="unit_id")


@dataclass(frozen=True)
class HrActor:
    user: object
    organization: object
    view_scope: UnitScope
    manage_scope: UnitScope
    view_as: bool = False

    @property
    def can_view(self) -> bool:
        return self.organization is not None and self.view_scope.has_structure_access

    @property
    def can_manage(self) -> bool:
        return self.organization is not None and not self.view_as and self.manage_scope.has_structure_access

    @property
    def org_wide(self) -> bool:
        return self.view_scope.is_org_wide

    def sees(self, contract) -> bool:
        if not self.can_view or contract.organization_id != getattr(self.organization, "pk", None):
            return False
        unit = getattr(contract, "unit", None)
        return unit_in_scope(self.view_scope, contract.unit_id, getattr(unit, "path", "") if unit else "")

    def manages(self, contract) -> bool:
        if not self.can_manage or contract.organization_id != getattr(self.organization, "pk", None):
            return False
        unit = getattr(contract, "unit", None)
        return unit_in_scope(self.manage_scope, contract.unit_id, getattr(unit, "path", "") if unit else "")

    def manages_unit(self, unit) -> bool:
        if not self.can_manage:
            return False
        if unit is None:
            return self.manage_scope.is_org_wide
        return unit_in_scope(self.manage_scope, unit.pk, unit.path)


def actor_for(user, organization, *, request=None, view_as: bool = False) -> HrActor:
    if organization is None or user is None or not getattr(user, "is_authenticated", False):
        return HrActor(user, None, EMPTY_SCOPE, EMPTY_SCOPE, view_as)
    manage = get_permission_scope(user, organization, PERM_MANAGE, request=request)
    view = _merge(get_permission_scope(user, organization, PERM_VIEW, request=request), manage)
    return HrActor(user, organization, view, EMPTY_SCOPE if view_as else manage, view_as)


def resolve_actor(request) -> HrActor:
    """Sorğudan aktor — ``request.organization`` (təşkilat middleware-i) və view-as bayrağı ilə."""
    return actor_for(
        getattr(request, "user", None),
        getattr(request, "organization", None),
        request=request,
        view_as=bool(getattr(request, "is_view_as", False)),
    )


def _membership_model():
    return django_apps.get_model("organizations", "Membership")


def staff_memberships(organization):
    """Təşkilatın aktiv HEYƏT üzvlükləri (tələbə ailəsi və valideyn rolları xaric)."""
    return (
        _membership_model()
        .objects.filter(organization=organization, is_active=True, role__is_active=True, user__is_active=True)
        .exclude(role__name__in=NON_EMPLOYEE_ROLE_NAMES)
    )


def is_eligible_employee(user_id, organization) -> bool:
    return bool(user_id) and staff_memberships(organization).filter(user_id=user_id).exists()


def staff_in_scope(organization, scope: UnitScope):
    """Əhatədəki heyət üzvlükləri — UNIT aktoru yalnız ``scope_unit``-i öz alt-ağacında olanları seçir."""
    rows = staff_memberships(organization)
    if scope.is_org_wide:
        return rows
    if not scope.is_unit_scoped:
        return rows.none()
    return rows.filter(scope.unit_subtree_q(path_field="scope_unit__path", id_field="scope_unit_id"))


def primary_unit(user_id, organization):
    """İşçinin əsas heyət üzvlüyünün bölməsi (forma ön-doldurması və xatırlatma alıcıları üçün)."""
    membership = (
        staff_memberships(organization)
        .filter(user_id=user_id, scope_unit__isnull=False)
        .select_related("scope_unit")
        .order_by("-is_primary", "-role__level")
        .first()
    )
    return membership.scope_unit if membership else None


__all__ = [
    "HrActor",
    "actor_for",
    "contracts_q",
    "is_eligible_employee",
    "primary_unit",
    "resolve_actor",
    "staff_in_scope",
    "staff_memberships",
    "unit_in_scope",
]
