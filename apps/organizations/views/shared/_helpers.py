"""Organizations — rollar-arası helper-lər (F5 rol-skeleti, 2026-07-02)."""

from django.utils.text import slugify

from ...models import OrgUnit
from ...scoping import scope_org_units
from ...services import is_tenant_accessible_organization


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


def _has_org_admin_alias(user, organization) -> bool:
    """Aktiv üzvlüklərdən biri `org_admin` alias-ı verirmi (mərkəzi alias qaydası).

    `ProfileRole.aliases_for_membership_role` — admin-ekvivalent ad (rektor,
    dekan, kafedra müdiri…) VƏ YA `level >= 80`, amma `ADMIN_ALIAS_EXEMPT_ROLE_NAMES`
    (imtahan mərkəzi, HR, Tədris şöbəsi rəhbəri) HEÇ VAXT.
    """
    from core.roles import ProfileRole

    from ...services import get_active_memberships

    for membership in get_active_memberships(user, organization):
        role = getattr(membership, "role", None)
        aliases = ProfileRole.aliases_for_membership_role(
            getattr(role, "name", ""), level=getattr(role, "level", 0) or 0
        )
        if ProfileRole.ORG_ADMIN in aliases:
            return True
    return False


def _can_manage_organization(user, organization):
    """İdarəetmə səviyyəli giriş: superadmin, təşkilat sahibi və ya `org_admin`
    alias-lı üzvlük.

    2026-09-12 (P1-11): əvvəl yalnız `can_user_manage_org` (xam `level >= 80`)
    idi — `ADMIN_ALIAS_EXEMPT_ROLE_NAMES` (imtahan mərkəzi rəhbəri 85, Tədris
    şöbəsi rəhbəri 85) nəzərə alınmırdı. Köhnə boş resolver bu ORGANIZATION
    rollarına (level < 90) struktur əhatəsi vermədiyi üçün yazma səthləri
    (fakültə/kafedra yaratma, redaktə, silmə, rəhbər təyini) onlara TƏSADÜFƏN
    bağlı qalırdı; sərt `get_permission_scope` `unit.view`-lu ORGANIZATION
    rolunu org-wide etdiyindən xam səviyyə qapısı imtahan mərkəzi rəhbərinə
    fakültə yaratmağı AÇARDI (yoxlanıldı). Rol kataloqunun qərarı açıqdır:
    muaf rollar «üzv/struktur idarəetməsi yox» — qapı həmin alias qaydasına
    bağlanır. Dekan / kafedra müdiri / rektorat (admin-ekvivalent adlar) və
    level ≥ 80 muaf olmayan xüsusi rollar üçün nəticə ƏVVƏLKİ KİMİDİR: alias
    qaydası köhnə səviyyə qaydasının ALT ÇOXLUĞUDUR (admin-ekvivalent adların
    hamısı `ROLE_LEVELS`/`ProfileRole.LEVELS`-də ≥ 80-dir), yəni qapı yalnız
    DARALIR, genişlənmir; sorğu sayı da dəyişmir (bir üzvlük SELECT-i).
    """
    if not _can_access_organization(user, organization):
        return False

    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True

    if getattr(organization, "owner_id", None) == getattr(user, "id", None):
        return True

    return _has_org_admin_alias(user, organization)


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
    """Struktur səthlərinin (legacy `org-structure`, fakültə/kafedra POST
    əməlləri, bölmə detal modalı) ƏHATƏSİ — `unit.view` açarına GÖRƏ.

    2026-09-12 (P1-11): əvvəl köhnə ümumi `get_unit_scope` işlənirdi — o, HƏR
    aktiv üzvlüyün `scope_unit`-ini toplayırdı, yəni dekanın başqa fakültənin
    kafedrasına MÜƏLLİM kimi təyinatı həmin kafedranı dekan kimi redaktə/silmə
    əhatəsinə salırdı. İndi əhatə YALNIZ `unit.view` daşıyan üzvlükdən çıxır
    (fakültə/kafedra kontekst qurucuları və ağac ekranı ilə EYNİ resolver —
    bax `structure_views/context.py::_structure_scope`, `tree.py::tree_scope`).
    `unit.view`-suz aktor `EMPTY_SCOPE` alır (fail-closed).
    """
    from ...scoping import get_permission_scope

    return get_permission_scope(request.user, organization, "unit.view", request=request)


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
