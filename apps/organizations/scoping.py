"""
Mərkəzi unit-scoping servisi.

Dekan / kafedra müdürü kimi UNIT-scope rollu istifadəçilərin görə bildiyi
məlumat sahəsini (öz fakültə/kafedra alt-ağacı) müəyyən edir.

Dizayn prinsipləri:
- `Membership.scope_unit` yeganə mənbədir (source of truth).
- Subtree hesablaması OrgUnit.path (materialized path) üzərində
  `path__startswith` ilə aparılır — rekursiya/N+1 yoxdur.
- Nəticə per-request memoizasiya olunur (`request._unit_scope_cache`) ki,
  sidebar + dashboard + siyahı sorğuları eyni request-də təkrar DB-yə getməsin.
- Cross-request cache QƏSDƏN yoxdur: rol/scope dəyişiklikləri dərhal
  qüvvəyə minməlidir (tenant izolyasiyası > mikro-performans).
"""

from dataclasses import dataclass, field

from django.db.models import Q, QuerySet

from core.constants import RoleScopeType
from core.permissions import has_permission

# from typing import Optional


# Org-wide görünüş üçün minimal idarəetmə levli (rector/vice_rector/org_admin/owner).
ORG_WIDE_MIN_LEVEL = 90


@dataclass(frozen=True)
class UnitScope:
    """
    İstifadəçinin aktiv təşkilatdakı struktur görünüş sahəsi.

    scope_type:
        "org"  — bütün təşkilat (rektor, prorektor, org admin/owner, superadmin,
                 ORGANIZATION-scope idarəetmə rolları, məs. imtahan mərkəzi/HR
                 öz permission-ları çərçivəsində)
        "unit" — yalnız scope_unit alt-ağac(lar)ı (dekan, kafedra müdürü, baş tələbə)
        "none" — struktur görünüşü yoxdur (adi tələbə/müəllim; onların scope-u
                 kurs/qrup üzvlüyü ilə ayrıca müəyyən olunur)
    """

    scope_type: str
    unit_ids: frozenset = field(default_factory=frozenset)
    unit_paths: tuple = field(default_factory=tuple)

    @property
    def is_org_wide(self) -> bool:
        return self.scope_type == "org"

    @property
    def is_unit_scoped(self) -> bool:
        return self.scope_type == "unit"

    @property
    def has_structure_access(self) -> bool:
        return self.scope_type in {"org", "unit"}

    def unit_subtree_q(self, path_field: str = "path", id_field: str = "id") -> Q:
        """
        OrgUnit queryset-i üçün alt-ağac filtri (öz unitlər + bütün törəmələri).
        Boş scope üçün heç nə uyğun gəlməyən Q qaytarır.
        """
        if self.is_org_wide:
            return Q()
        if not self.unit_paths:
            return Q(pk__in=[])
        q = Q(**{f"{id_field}__in": list(self.unit_ids)})
        for path in self.unit_paths:
            q |= Q(**{f"{path_field}__startswith": f"{path}/"})
        return q


ORG_WIDE_SCOPE = UnitScope(scope_type="org")
EMPTY_SCOPE = UnitScope(scope_type="none")


def _resolve_unit_scope(user, organization) -> UnitScope:
    from apps.organizations.models import OrgUnit
    from apps.organizations.services import get_active_memberships

    if not user or not getattr(user, "is_authenticated", False) or organization is None:
        return EMPTY_SCOPE

    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return ORG_WIDE_SCOPE

    if getattr(organization, "owner_id", None) == user.id:
        return ORG_WIDE_SCOPE

    memberships = list(get_active_memberships(user, organization))
    if not memberships:
        return EMPTY_SCOPE

    scoped_unit_ids = set()
    for membership in memberships:
        role = membership.role
        # ORGANIZATION scope-lu yüksək idarəetmə rolu → bütün təşkilat.
        if role.scope_type == RoleScopeType.ORGANIZATION and role.level >= ORG_WIDE_MIN_LEVEL:
            return ORG_WIDE_SCOPE
        # UNIT scope-lu rol konkret unitə bağlanıbsa → həmin alt-ağac.
        if membership.scope_unit_id:
            scoped_unit_ids.add(membership.scope_unit_id)

    if not scoped_unit_ids:
        return EMPTY_SCOPE

    # Tək sorğu ilə path-ləri götürürük (subtree filtrləri üçün lazımdır).
    unit_rows = OrgUnit.objects.filter(organization=organization, pk__in=scoped_unit_ids, is_active=True).values_list(
        "pk", "path"
    )
    unit_ids = frozenset(pk for pk, _ in unit_rows)
    unit_paths = tuple(path for _, path in unit_rows if path)
    if not unit_ids:
        return EMPTY_SCOPE
    return UnitScope(scope_type="unit", unit_ids=unit_ids, unit_paths=unit_paths)


def get_unit_scope(user, organization, request=None) -> UnitScope:
    """
    İstifadəçinin təşkilatdakı unit scope-unu qaytarır (per-request cache ilə).
    """
    user_id = getattr(user, "pk", None)
    org_id = getattr(organization, "pk", None)
    cache_key = (user_id, org_id)

    if request is not None and user_id is not None and org_id is not None:
        cache = getattr(request, "_unit_scope_cache", None)
        if cache is None:
            cache = {}
            try:
                request._unit_scope_cache = cache
            except Exception:  # noqa: BLE001 — bəzi request obyektləri immutable ola bilər
                cache = None
        if cache is not None and cache_key in cache:
            return cache[cache_key]

    scope = _resolve_unit_scope(user, organization)

    if request is not None and user_id is not None and org_id is not None:
        cache = getattr(request, "_unit_scope_cache", None)
        if cache is not None:
            cache[cache_key] = scope

    return scope


def get_permission_scope(user, organization, permission: str, request=None) -> UnitScope:
    """Resolve structural scope only from memberships granting ``permission``.

    A UNIT-scoped role without a valid ``scope_unit`` grants no structural
    access.  This deliberately differs from the legacy generic scope resolver:
    an unrelated membership must never lend its unit to a privileged role.
    """
    user_id = getattr(user, "pk", None)
    org_id = getattr(organization, "pk", None)
    cache_key = ("permission", user_id, org_id, permission)
    if request is not None:
        cache = getattr(request, "_unit_scope_cache", None)
        if cache is None:
            cache = {}
            request._unit_scope_cache = cache
        if cache_key in cache:
            return cache[cache_key]

    if not user or not getattr(user, "is_authenticated", False) or organization is None:
        scope = EMPTY_SCOPE
    elif getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        scope = ORG_WIDE_SCOPE
    elif getattr(organization, "owner_id", None) == user_id:
        scope = ORG_WIDE_SCOPE
    else:
        from apps.organizations.models import Membership, OrgUnit

        memberships = Membership.objects.filter(
            user=user,
            organization=organization,
            is_active=True,
            role__organization=organization,
            role__is_active=True,
        ).select_related("role", "scope_unit")
        unit_ids = set()
        scope = EMPTY_SCOPE
        for membership in memberships:
            role = membership.role
            if not has_permission(list(role.permissions or []), permission):
                continue
            if role.scope_type == RoleScopeType.ORGANIZATION:
                scope = ORG_WIDE_SCOPE
                break
            if role.scope_type == RoleScopeType.UNIT and membership.scope_unit_id:
                unit_ids.add(membership.scope_unit_id)
        if not scope.is_org_wide and unit_ids:
            rows = OrgUnit.objects.filter(
                organization=organization,
                pk__in=unit_ids,
                is_active=True,
            ).values_list("pk", "path")
            resolved = list(rows)
            if resolved:
                scope = UnitScope(
                    scope_type="unit",
                    unit_ids=frozenset(pk for pk, _path in resolved),
                    unit_paths=tuple(path for _pk, path in resolved if path),
                )

    if request is not None:
        request._unit_scope_cache[cache_key] = scope
    return scope


def scope_org_units(queryset: QuerySet, scope: UnitScope) -> QuerySet:
    """OrgUnit queryset-ini scope-a görə məhdudlaşdırır."""
    if scope.is_org_wide:
        return queryset
    if not scope.is_unit_scoped:
        return queryset.none()
    return queryset.filter(scope.unit_subtree_q())


def scope_memberships_by_unit(queryset: QuerySet, scope: UnitScope, organization=None) -> QuerySet:
    """
    Membership queryset-ini scope-a görə məhdudlaşdırır:
    yalnız scope alt-ağacındakı unitlərə bağlı üzvlüklər görünür.

    Performans: alt-ağac unit id-ləri tək subquery ilə alınır;
    Membership üzərində scope_unit__in filtri index-lənmiş FK-dır.
    """
    if scope.is_org_wide:
        return queryset
    if not scope.is_unit_scoped:
        return queryset.none()

    from apps.organizations.models import OrgUnit

    subtree_unit_ids = OrgUnit.objects.filter(scope.unit_subtree_q())
    if organization is not None:
        subtree_unit_ids = subtree_unit_ids.filter(organization=organization)
    return queryset.filter(scope_unit__in=subtree_unit_ids.values("pk"))


__all__ = [
    "EMPTY_SCOPE",
    "ORG_WIDE_SCOPE",
    "ORG_WIDE_MIN_LEVEL",
    "UnitScope",
    "get_unit_scope",
    "get_permission_scope",
    "scope_memberships_by_unit",
    "scope_org_units",
]


def user_scope_subtree_q(user, organization, *, path_field, id_field, permission=None):
    """İstifadəçinin unit alt-ağacı üçün filtr Q-su — ixtiyari sahə prefiksi ilə.

    `user_scope_covers_unit` bir unit üçün bool qaytarır; siyahı/aqreqat
    sorğularını daraltmaq üçünsə QUERYSET filtri lazımdır. Məsələn analitika
    `Enrollment`-ləri `offering__group` üzərindən daraldır:

        user_scope_subtree_q(u, org,
                             path_field="offering__group__path",
                             id_field="offering__group__id")

    ``None`` qaytarılır = «filtr tətbiq etmə». Bu, İKİ halda baş verir və hər
    ikisi ``user_scope_covers_unit`` ilə EYNİ semantikadır — fərqli davransalar
    eyni istifadəçi bir yerdə hər şeyi görər, başqa yerdə heç nə:

      1. Scope org-səviyyəlidir (rektor, admin, org sahibi).
      2. Scope ÜMUMİYYƏTLƏ təyin olunmayıb (``has_structure_access`` yalan) —
         strukturu hələ qurmamış təşkilatlar. Burada bağlı davransaq, heç bir
         ``Membership.scope_unit`` təyin etməmiş hər universitetdə dekan BOŞ
         analitika paneli görərdi; yəni məhdudiyyət deyil, sıradan çıxma olardı.

    Boş ``Q()`` əvəzinə ``None`` seçilib ki, çağıran niyyəti açıq yazsın və bu,
    təsadüfən «heç nə uyğun gəlmir» (``Q(pk__in=[])``) ilə qarışmasın.
    """
    if permission:
        scope = get_permission_scope(user, organization, permission)
        return scope.unit_subtree_q(path_field=path_field, id_field=id_field)
    scope = get_unit_scope(user, organization)
    if scope.is_org_wide or not scope.has_structure_access:
        return None
    return scope.unit_subtree_q(path_field=path_field, id_field=id_field)


def user_scope_covers_unit(user, organization, unit_id, permission=None) -> bool:
    """İstifadəçinin unit alt-ağacı verilmiş bölməni əhatə edirmi.

    MODUL SƏRHƏDİ: bu yoxlama registrar-dan (jurnal təsdiqi) lazımdır, lakin
    registrar ``apps.organizations``-u Python səviyyəsində İMPORT ETMİR — əks
    halda ``organizations ↔ registrar`` dövrü yaranır (organizations seed əmri
    registrar-ı import edir). Registrar organizations modellərini yalnız app
    registry ilə həll edir (bax ``apps/registrar/public.py`` şərhinə), ona görə
    məntiq burada, öz modulunda qalır və modeldən nazik delegator ilə çağırılır.

    ``unit_id`` ``None``-dursa ``False`` — unit-scope istifadəçi üçün aidiyyəti
    müəyyən deyil, org-wide səlahiyyət tələb olunur.

    Scope ÜMUMİYYƏTLƏ təyin edilməyibsə ``True`` qaytarılır: qərar çağırana
    qalır. Bu, strukturu hələ qurmamış təşkilatlarda mövcud davranışı saxlayır.
    """
    from .models import OrgUnit

    scope = get_permission_scope(user, organization, permission) if permission else get_unit_scope(user, organization)
    if permission and not scope.has_structure_access:
        return False
    if scope.is_org_wide or not scope.has_structure_access:
        return True
    if unit_id is None:
        return False
    return OrgUnit.objects.filter(scope.unit_subtree_q()).filter(pk=unit_id).exists()
