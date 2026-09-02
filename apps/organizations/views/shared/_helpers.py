"""Organizations — rollar-arası helper-lər (F5 rol-skeleti, 2026-07-02)."""

from django.utils.text import slugify

from ...models import OrgUnit
from ...scoping import scope_org_units
from ...services import can_user_manage_org, is_tenant_accessible_organization


def _is_ajax_request(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _can_access_organization(user, organization):
    if not getattr(user, "is_authenticated", False):
        return False

    if not is_tenant_accessible_organization(organization):
        return False

    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True

    if getattr(organization, "owner_id", None) == user.id:
        return True

    return user.memberships.filter(organization=organization, organization__status="active", is_active=True).exists()


def _can_manage_organization(user, organization):
    if not _can_access_organization(user, organization):
        return False

    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True

    return can_user_manage_org(user, organization)


def _can_view_role_matrix(user, organization) -> bool:
    """Rol kataloqunu / icazə matrisini kim OXUYA bilər.

    2026-09-02 audit, P2-2: səhifə ``_can_manage_organization``-a bağlı idi, o
    da ``level >= 80`` üçün implicit ``org_admin`` alias-ını qəbul edir — yəni
    BİR FAKÜLTƏYƏ scope-lanmış DEKAN bütün təşkilatın rol kataloqunu və icazə
    matrisini görürdü (oxu-səviyyəli açıqlama; POST onsuz da heç nə dəyişmirdi).

    İndi tələb konkret açardır: ``role.view`` (HR, rektor/owner wildcard ilə).
    Superadmin və təşkilat sahibi istisnadır.
    """
    from core.permissions import has_permission

    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    if getattr(organization, "owner_id", None) == getattr(user, "id", None):
        return True

    permissions: set[str] = set()
    for membership in user.memberships.filter(
        organization=organization,
        is_active=True,
        role__is_active=True,
    ).select_related("role"):
        permissions.update(membership.role.permissions or [])
    return has_permission(list(permissions), "role.view")


def _has_org_permission(request, permission):
    from ...permissions import has_permission

    return has_permission(list(getattr(request, "org_permissions", []) or []), permission)


def _unique_unit_slug(organization, name, fallback):
    base_slug = slugify(name) or fallback
    slug = base_slug
    suffix = 2
    while OrgUnit.objects.filter(organization=organization, slug=slug).exists():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug


def _get_structure_scope(request, organization):
    from ...scoping import get_unit_scope

    return get_unit_scope(request.user, organization, request=request)


def _can_view_structure(request, organization, scope):
    return scope.is_org_wide or _has_org_permission(request, "unit.view")


def _visible_units_queryset(organization, scope):
    """Scope-a görə görünən OrgUnit-lər — FAIL-CLOSED.

    TƏHLÜKƏSİZLİK: əvvəl scope nə org-wide, nə unit-scoped olanda (yəni
    ``EMPTY_SCOPE`` — məs. scope_unit təyin edilməmiş dekan) HEÇ BİR filtr
    tətbiq olunmurdu və istifadəçi bütün təşkilat strukturunu görüb redaktə edə
    bilirdi. Kanonik :func:`scope_org_units` bu halda ``none()`` qaytarır — ona
    delegate edirik ki, iki fərqli davranış qalmasın.
    """
    units = OrgUnit.objects.filter(organization=organization, is_active=True)
    return scope_org_units(units, scope)
