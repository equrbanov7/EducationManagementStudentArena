"""Görünüş və əməl icazələri — fail-closed.

İki ayrı sual var və onları qarışdırmaq təhlükəlidir:

``can_view``  — «bu müraciəti OXUYA bilərmi?» Sahib, cari şöbənin əhatəli
                emalçısı, İZLƏYƏN şöbənin əhatəli emalçısı, ``application.manage``
                daşıyan (RİM/rektor/prorektor), superuser və təşkilat sahibi.
``can_act``   — «bu müraciətə QƏRAR verə bilərmi?» YALNIZ CARİ şöbənin əhatəli
                emalçısı və müraciət AÇIQ olduqda. İzləyən şöbə OXUYUR, ƏMƏL ETMİR.

«Əhatə» ölçüsü: şöbənin ``resolve_by``-ı ``organization``-dursa rol adı
kifayətdir; əks halda üzvlüyün ``scope_unit``-i müraciətin
``current_scope_unit``-ini path prefiksi ilə örtməlidir.
"""

from __future__ import annotations

from django.db.models import Q

from apps.organizations.unit_heads import ancestor_unit_ids
from core.constants import RoleScopeType
from core.permissions import has_permission

from ..constants import PERM_MANAGE, ResolveBy
from ..models import ApplicationUnit


def _is_privileged(user, organization) -> bool:
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    return organization is not None and getattr(organization, "owner_id", None) == user.pk


def active_memberships(user, organization):
    from apps.organizations.models import Membership

    if user is None or organization is None or not getattr(user, "is_authenticated", False):
        return []
    cached = getattr(user, "_applications_memberships", None)
    if cached is not None and cached[0] == organization.pk:
        return cached[1]
    memberships = list(
        Membership.objects.filter(
            user=user,
            organization=organization,
            is_active=True,
            role__organization=organization,
            role__is_active=True,
        ).select_related("role", "scope_unit")
    )
    try:
        user._applications_memberships = (organization.pk, memberships)
    except Exception:  # noqa: BLE001 — AnonymousUser kimi obyektlər immutable ola bilər
        pass
    return memberships


def active_units(organization) -> list:
    """Təşkilatın aktiv ``ApplicationUnit`` kataloqu — request daxilində keşlənir.

    ``handled_unit_ids`` (bir kontekst qurulmasında 7-8 dəfə: ``is_handler_anywhere``,
    tab sayğacları, KPI-lar, ``handled_unit_names``) və marşrutlaşdırma
    (``routing.unit_by_code``) eyni kataloqu dəfələrlə sorğulayırdı — keş olmadan
    hər çağırış ayrı SELECT idi (QA P2-26/P2-6: bölmə açılışında 80+ sorğu, 37-42
    dublikat). ``active_memberships``-dəki eyni keş naxışı (obyekt-atributu).
    """
    if organization is None:
        return []
    cached = getattr(organization, "_applications_units_cache", None)
    if cached is not None:
        return cached
    units = list(ApplicationUnit.objects.filter(organization=organization, is_active=True).order_by("order", "name"))
    try:
        organization._applications_units_cache = units
    except Exception:  # noqa: BLE001 — dəyişməz obyektlər üçün (nadir)
        pass
    return units


def user_permissions(user, organization) -> list:
    permissions = set()
    for membership in active_memberships(user, organization):
        permissions.update(membership.role.permissions or [])
    return list(permissions)


def has_app_permission(user, organization, permission: str) -> bool:
    if _is_privileged(user, organization):
        return True
    return has_permission(user_permissions(user, organization), permission)


def _covers(membership, scope_unit_id, scope_unit_path) -> bool:
    """Üzvlük verilmiş aidiyyət bölməsini örtürmü."""
    if membership.role.scope_type == RoleScopeType.ORGANIZATION:
        return True
    if scope_unit_id is None:
        # Aidiyyət təyin olunmayıb (mərkəzi şöbə və ya əcdad tapılmadı) →
        # rol adı kifayətdir; daraltmaq üçün struktur məlumat yoxdur.
        return True
    if not membership.scope_unit_id:
        return False
    ancestors = set(scope_unit_path or [])
    return str(membership.scope_unit_id) in ancestors


def handles_unit(user, organization, unit: ApplicationUnit, scope_unit) -> bool:
    """İstifadəçi verilmiş şöbəni (verilmiş aidiyyətlə) emal edirmi."""
    if unit is None:
        return False
    role_names = set(unit.role_names)
    if not role_names:
        return False
    scope_unit_id = getattr(scope_unit, "pk", None) if scope_unit is not None else None
    scope_path = ancestor_unit_ids(scope_unit) if scope_unit is not None else []
    if unit.resolve_by == ResolveBy.ORGANIZATION.value:
        scope_unit_id = None
    for membership in active_memberships(user, organization):
        if membership.role.name in role_names and _covers(membership, scope_unit_id, scope_path):
            return True
    return False


def handler_role_for(user, organization, unit: ApplicationUnit) -> str:
    """Aktorun bu şöbədəki rol adı (audit/hadisə snapshot-u üçün)."""
    if unit is None:
        return ""
    role_names = set(unit.role_names)
    for membership in active_memberships(user, organization):
        if membership.role.name in role_names:
            return membership.role.name
    memberships = active_memberships(user, organization)
    return memberships[0].role.name if memberships else ""


def handled_unit_ids(user, organization) -> set:
    """İstifadəçinin rol adına görə emal edə biləcəyi bütün şöbələr."""
    role_names = {membership.role.name for membership in active_memberships(user, organization)}
    if not role_names:
        return set()
    return {unit.pk for unit in active_units(organization) if role_names & set(unit.role_names)}


def is_handler_anywhere(user, organization) -> bool:
    return bool(handled_unit_ids(user, organization))


def can_view(user, application) -> bool:
    organization = application.organization
    if _is_privileged(user, organization):
        return True
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if application.created_by_id == user.pk:
        return True
    if has_permission(user_permissions(user, organization), PERM_MANAGE):
        return True
    if handles_unit(user, organization, application.current_unit, application.current_scope_unit):
        return True
    for watch in application.watches.select_related("unit", "scope_unit"):
        if handles_unit(user, organization, watch.unit, watch.scope_unit):
            return True
    return False


def can_act(user, application) -> bool:
    """QƏRAR hüququ — yalnız CARİ şöbənin emalçısı, müraciət açıq ikən.

    İzləyən şöbə DAXİL DEYİL (dizayn §6: «only if request.current_unit ==
    user.unit»). Superuser istisna olaraq daxildir — platforma səviyyəli
    dəstək/bərpa əməlləri üçün.
    """
    if not application.is_open:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    return handles_unit(user, application.organization, application.current_unit, application.current_scope_unit)


def can_see_internal(user, application) -> bool:
    """Daxili qeydləri GÖRMƏ hüququ — statusdan ASILI DEYİL (QA 2026-09-05 APPLICATIONS-08).

    ``can_act`` (qərar hüququ) müraciət bağlananda/yönləndiriləndə False olur və
    emalçı ÖZ yazdığı daxili qeydi də görmürdü. Görmə: superuser, `application.manage`
    daşıyıcısı, cari şöbənin emalçısı və ya izləyən (watch) şöbənin emalçısı.
    """
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    organization = application.organization
    if has_app_permission(user, organization, PERM_MANAGE):
        return True
    if handles_unit(user, organization, application.current_unit, application.current_scope_unit):
        return True
    for watch in application.watches.select_related("unit", "scope_unit"):
        if handles_unit(user, organization, watch.unit, watch.scope_unit):
            return True
    return False


def is_sender(user, application) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and application.created_by_id == user.pk)


def inbox_q(user, organization) -> Q:
    """«Mənə gələnlər» filtri — emal etdiyi şöbə + əhatəli aidiyyət.

    Org-scope üzvlük üçün aidiyyət məhdudiyyəti yoxdur; unit-scope üzvlük üçün
    ``current_scope_unit`` üzvlüyün alt-ağacında olmalıdır (``path`` prefiksi)
    və ya ümumiyyətlə təyin olunmamalıdır.
    """
    unit_ids = handled_unit_ids(user, organization)
    if not unit_ids:
        return Q(pk__in=[])

    memberships = active_memberships(user, organization)
    if any(membership.role.scope_type == RoleScopeType.ORGANIZATION for membership in memberships):
        return Q(current_unit_id__in=unit_ids)

    scope_q = Q(current_scope_unit__isnull=True)
    for membership in memberships:
        scope_unit = membership.scope_unit
        if scope_unit is None:
            continue
        scope_q |= Q(current_scope_unit_id=scope_unit.pk) | Q(
            current_scope_unit__path__startswith=f"{scope_unit.path}/"
        )
    return Q(current_unit_id__in=unit_ids) & scope_q


def watching_q(user, organization) -> Q:
    unit_ids = handled_unit_ids(user, organization)
    if not unit_ids:
        return Q(pk__in=[])
    return Q(watches__unit_id__in=unit_ids) & ~Q(current_unit_id__in=unit_ids)


def visible_q(user, organization) -> Q:
    """İstifadəçinin ÜMUMİYYƏTLƏ görə bildiyi müraciətlər (bütün tablar)."""
    if _is_privileged(user, organization) or has_permission(user_permissions(user, organization), PERM_MANAGE):
        return Q()
    return Q(created_by=user) | inbox_q(user, organization) | watching_q(user, organization)


__all__ = [
    "active_memberships",
    "active_units",
    "can_act",
    "can_view",
    "handled_unit_ids",
    "handler_role_for",
    "handles_unit",
    "has_app_permission",
    "inbox_q",
    "is_handler_anywhere",
    "is_sender",
    "user_permissions",
    "visible_q",
    "watching_q",
]
