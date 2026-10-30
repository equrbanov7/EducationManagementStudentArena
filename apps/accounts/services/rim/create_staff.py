"""Staff role/scope selection through existing catalogue and permission scopes."""

from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

from apps.organizations.models import OrgUnit
from apps.organizations.public import get_permission_scope, get_user_org_role_level
from core.constants import RoleScopeType

from ..role_catalog import assignable_roles, is_admin_role, is_owner_role, role_label
from .search import STUDENT_ROLE_NAMES

_CTX = "profile.rim"


def can_assign_staff(actor):
    return actor.has("role.assign") or actor.has("org.manage_members")


def _assignment_scope(actor):
    scope = get_permission_scope(actor.user, actor.organization, "role.assign")
    if not scope.has_structure_access:
        scope = get_permission_scope(actor.user, actor.organization, "org.manage_members")
    return scope


def _scopes(actor):
    return (
        _assignment_scope(actor),
        get_permission_scope(actor.user, actor.organization, "user.import_staff"),
    )


def staff_roles(actor):
    if not can_assign_staff(actor):
        return []
    scopes = _scopes(actor)
    level = actor.level if actor.is_superadmin else get_user_org_role_level(actor.user, actor.organization)
    roles = assignable_roles(actor.organization, actor_level=level, is_superadmin=actor.is_superadmin)
    result = []
    for role in roles:
        if role.name in STUDENT_ROLE_NAMES or role.scope_type not in (RoleScopeType.UNIT, RoleScopeType.ORGANIZATION):
            continue
        if is_owner_role(role) and not actor.has("org.owner.assign"):
            continue
        if is_admin_role(role) and not any(
            actor.has(key) for key in ("org.owner.assign", "org.admin.assign", "user.grant_privileged")
        ):
            continue
        if role.scope_type == RoleScopeType.ORGANIZATION and not all(scope.is_org_wide for scope in scopes):
            continue
        result.append(role)
    return result


def staff_units(actor):
    queryset = OrgUnit.objects.filter(organization=actor.organization, is_active=True)
    for scope in _scopes(actor):
        if not scope.has_structure_access:
            return queryset.none()
        if not scope.is_org_wide:
            queryset = queryset.filter(scope.unit_subtree_q())
    return queryset


def validate_staff_assignment(actor, data, draft):
    """Fill a validated draft; reject unknown/foreign/inactive/elevated roles."""
    roles = {str(role.pk): role for role in staff_roles(actor)}
    role = roles.get(str(data.get("role") or "").strip())
    if role is None:
        draft.errors["role"] = pgettext(_CTX, "Vəzifə seçilməyib və ya bu rolu təyin etmək üçün icazəniz yoxdur.")
        return None
    raw_unit = str(data.get("unit") or "").strip()
    unit = None
    if raw_unit:
        try:
            unit = staff_units(actor).filter(pk=raw_unit).first()
        except (ValidationError, ValueError, TypeError):
            pass
        if unit is None:
            draft.errors["unit"] = pgettext(_CTX, "Bölmə tapılmadı və ya icazə əhatənizdən kənardadır.")
    if role.scope_type == RoleScopeType.UNIT and unit is None:
        draft.errors.setdefault("unit", pgettext(_CTX, "Bu vəzifə üçün kafedra və ya bölmə seçin."))
    if role.scope_type == RoleScopeType.ORGANIZATION and raw_unit:
        draft.errors["unit"] = pgettext(_CTX, "Bu rol təşkilatı bütövlükdə əhatə edir; bölmə sahəsini boş saxlayın.")
    draft.scope_unit = unit
    draft.values["title"] = str(role_label(role))
    draft.values["department"] = unit.name if unit else ""
    return role


def search_staff_catalog(actor, *, catalog, query, limit, offset):
    from core.search_text import tolerant_match, tolerant_q

    from .create import require_create
    from .create_options import _bounds

    require_create(actor, "staff")
    limit, offset = _bounds(limit, offset)
    if catalog == "staff_role":
        text = str(query or "").strip()[:120]
        roles = [role for role in staff_roles(actor) if tolerant_match(text, str(role_label(role)), role.name)]
        window = roles[offset : offset + limit + 1]
        results = [{"id": str(role.pk), "text": str(role_label(role)), "hint": ""} for role in window[:limit]]
    else:
        queryset = staff_units(actor)
        search = tolerant_q(str(query or "").strip()[:120], ("name",), compact_fields=("code",))
        if search is not None:
            queryset = queryset.filter(search)
        window = list(queryset.order_by("name", "pk")[offset : offset + limit + 1])
        results = [{"id": str(unit.pk), "text": unit.name, "hint": unit.code or ""} for unit in window[:limit]]
    return {"results": results, "has_more": len(window) > limit}
