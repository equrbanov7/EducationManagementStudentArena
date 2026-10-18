"""«Alt qrupa yerləşdirmə» — aktor qapısı (açarla, rol adı ilə YOX; sahib 2026-10-18).

Açar ``retake.manage`` (dekanlıq / tədris şöbəsi / RİM — kataloq: ``organizations.permissions_accounting``).
Əhatə mövcud struktur-scope məntiqinə tabedir (``OrgUnit.user_permission_scope``): ORGANIZATION rolu bütün
təşkilat, UNIT rolu yalnız öz alt-ağacındakı qrupların tələbələri. Hədəf jurnal (başqa fakültənin ümumi
fənni ola bilər) əhatə ilə məhdudlaşdırılmır — tələbə aktorun əhatəsində olmalıdır. Fail-closed:

* açar yoxdursa → ``FORBIDDEN`` (HTTP 403);
* açar var, tələbə əhatədən kənardır → ``OUT_OF_SCOPE`` (HTTP 404 — mövcudluq sızmasın).

Registrar ``organizations`` modellərini app registry ilə oxuyur (modul qrafı dövrsüz qalsın — ``public.py``).
"""

from __future__ import annotations

from django.apps import apps as django_apps

from core.constants import OrgUnitType

#: Yerləşdirmə açarı — 25% təkrar imtahan axını ilə EYNİ (dekan alt qrup müraciətini təsdiqləyir).
PLACEMENT_PERMISSION = "retake.manage"


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def _scope(user, organization):
    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    return org_unit_model.user_permission_scope(user, organization, PLACEMENT_PERMISSION)


def _membership_has_key(user, organization) -> bool:
    from core.permissions import has_permission

    membership_model = django_apps.get_model("organizations", "Membership")
    permissions: set = set()
    for role_permissions in membership_model.objects.filter(
        user=user, organization=organization, is_active=True, role__is_active=True
    ).values_list("role__permissions", flat=True):
        permissions.update(role_permissions or [])
    return has_permission(list(permissions), PLACEMENT_PERMISSION)


def has_placement_key(user, organization) -> bool:
    """Aktorun ümumiyyətlə yerləşdirmə açarı varmı (yoxdursa HTTP 403)."""
    if user is None or organization is None or not getattr(user, "is_authenticated", False):
        return False
    if _is_superadmin(user):
        return True
    if getattr(organization, "owner_id", None) == user.pk:
        return True
    return _membership_has_key(user, organization)


def scoped_groups(user, organization):
    """Aktorun əhatəsindəki AKTİV akademik qruplar (fail-closed)."""
    org_unit_model = django_apps.get_model("organizations", "OrgUnit")
    queryset = org_unit_model.objects.filter(organization=organization, is_active=True, unit_type=OrgUnitType.GROUP)
    if _is_superadmin(user):
        return queryset
    scope = _scope(user, organization)
    if not scope.has_structure_access:
        return queryset.none()
    if scope.is_org_wide:
        return queryset
    return queryset.filter(scope.unit_subtree_q())


def is_org_wide(user, organization) -> bool:
    if _is_superadmin(user):
        return True
    scope = _scope(user, organization)
    return bool(scope.has_structure_access and scope.is_org_wide)


def group_in_scope(user, organization, group_id) -> bool:
    """Tələbənin qrupu aktorun alt-ağacındadırmı."""
    if group_id is None:
        return False
    if is_org_wide(user, organization):
        return True
    return scoped_groups(user, organization).filter(pk=group_id).exists()


__all__ = ["PLACEMENT_PERMISSION", "group_in_scope", "has_placement_key", "is_org_wide", "scoped_groups"]
