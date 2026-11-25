"""OXU əhatəsinin fakültəyə genişlənməsindən QƏSDƏN kənar qalan rollar (sahib 2026-11-25).

``scoping.faculty_read_scope`` qrup / ixtisas / kafedra köklərini ən yaxın fakültəyə genişləndirir (tyutor, kafedra
müdiri — sahib 2026-10-14). «Əcnəbi tələbələrlə iş şöbəsi» isə yalnız əcnəbi QRUPLARINI görməlidir: o qruplar
«Lifelong» fakültəsində başqa qruplarla yan-yanadır, genişlənsə şöbə bütün fakültəni görərdi.

Qayda ROL ADINA baxır (``default_roles_foreign_office.EXACT_SCOPE_ROLE_NAMES``): bu rolların ``scope_unit`` kökləri
olduğu kimi qalır; eyni istifadəçinin BAŞQA rollarının kökləri (məs. proqram koordinatoru) əvvəlki kimi genişlənir.
Eyni vahid həm dəqiq, həm adi rolla verilibsə adi qayda qalib gəlir (heç kim əvvəlkindən az görmür).
Sorğu: üzvlüklər memoizasiya olunmuşdur; dəqiq köklərin yolları ən çoxu BİR sorğu (``_resolve_active_unit_paths``).
"""

from __future__ import annotations

from core.constants import RoleScopeType
from core.permissions import has_permission

from .default_roles_foreign_office import EXACT_SCOPE_ROLE_NAMES


def exact_scope_unit_ids(user, organization, permission: str) -> frozenset:
    """``permission`` daşıyan və YALNIZ dəqiq-əhatəli rollardan gələn ``scope_unit`` id-ləri."""
    from .scoping import _permission_scope_memberships

    exact, other = set(), set()
    for membership in _permission_scope_memberships(user, organization):
        role = membership.role
        if role.scope_type != RoleScopeType.UNIT or not membership.scope_unit_id:
            continue
        if not has_permission(list(role.permissions or []), permission):
            continue
        (exact if role.name in EXACT_SCOPE_ROLE_NAMES else other).add(membership.scope_unit_id)
    return frozenset(exact - other)


def widen_except_exact(user, organization, permission: str, scope, request=None):
    """``widen_chair_scope_to_faculty`` — dəqiq-əhatəli rolların kökləri istisna olmaqla."""
    from .scoping import UnitScope, _resolve_active_unit_paths, widen_chair_scope_to_faculty

    if not scope.is_unit_scoped or organization is None:
        return scope
    pinned = exact_scope_unit_ids(user, organization, permission) & frozenset(scope.unit_ids)
    if not pinned:
        return widen_chair_scope_to_faculty(organization, scope, request=request)
    rest = frozenset(scope.unit_ids) - pinned
    widened_ids, widened_paths = frozenset(), ()
    if rest:
        rest_rows = _resolve_active_unit_paths(user, organization, rest)
        rest_scope = UnitScope(
            scope_type="unit",
            unit_ids=frozenset(pk for pk, _path in rest_rows),
            unit_paths=tuple(path for _pk, path in rest_rows if path),
            excluded_unit_ids=scope.excluded_unit_ids,
        )
        widened = widen_chair_scope_to_faculty(organization, rest_scope, request=request)
        widened_ids, widened_paths = widened.unit_ids, widened.unit_paths
    pinned_rows = _resolve_active_unit_paths(user, organization, pinned)
    paths = list(widened_paths)
    for _pk, path in pinned_rows:
        if path and path not in paths:
            paths.append(path)
    return UnitScope(
        scope_type="unit",
        unit_ids=frozenset(widened_ids) | frozenset(pk for pk, _path in pinned_rows),
        unit_paths=tuple(paths),
        excluded_unit_ids=scope.excluded_unit_ids,
    )


__all__ = ["exact_scope_unit_ids", "widen_except_exact"]
