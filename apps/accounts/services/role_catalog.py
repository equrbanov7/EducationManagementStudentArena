"""Təşkilat rol kataloqu — «Rol təyin et» və «Rolları idarə et» üçün TƏK MƏNBƏ.

KÖK SƏBƏB (sahib şikayəti 2026-09-09: «bir nəfərə həm proqram koordinatoru, həm
müəllim verirəm — proqram koordinatoru rolunu görmürəm»).

İki ekran İKİ FƏRQLİ kataloqdan oxuyurdu:

* «Rol təyin et» → ``organizations.Role`` (dekan, kafedra müdiri, proqram
  koordinatoru, tyutor, laborant… — onlarla rol);
* «Rolları idarə et» → köhnə ``core.roles.ProfileRole.CHOICES`` enum-u
  (14 ad; ``program_coordinator``, ``dean``, ``tutor`` və s. YOXDUR).

Nəticə: təşkilat rolu olan şəxsin həmin rolu ikinci ekranda nə badge kimi
görünürdü, nə də verilə bilirdi. Daha pisi — ``_sync_user_role_memberships``
``map_org_role_to_profile_role`` ilə ``program_coordinator``-u (level 45)
``member``-ə xəritələyir, ``member`` isə redaktə oluna bilən dəstdədir; yəni
həmin ekranda «Yadda saxla» basmaq koordinator üzvlüyünü SƏSSİZCƏ söndürürdü.

Bu modul rolları BİR yerdən — təşkilatın öz ``Role`` kataloqundan — verir.
``UserProfile.role`` sahəsi əvvəlki kimi denormallaşdırılmış «əsas rol» olaraq
qalır (geriyə uyğunluq); onu ``sync_profile_primary_role`` yeniləyir.

Burada YALNIZ oxu/xəritələmə var — icazə qapıları çağıran qatdadır.
"""

from __future__ import annotations

from core.constants import ROLE_LEVELS
from core.roles import ProfileRole, resolve_seeded_role_label

#: Sətir/badge-lərdə göstərilən maksimum rol sayı (qalanı «+N» ilə yığılır).
ROLE_CHIP_PREVIEW = 3

#: Səhifə ölçüsü — hər iki reyestr eyni ritmdə səhifələnir.
PAGE_SIZE = 15


# ─── Etiket / göstərim ──────────────────────────────────────────────────────


def role_label(role) -> str:
    """``Role.display_name`` — seed-dən qalmış İngiliscə ad AZ-a çevrilir."""
    return resolve_seeded_role_label(getattr(role, "name", ""), getattr(role, "display_name", ""))


def display_name(user) -> str:
    full_name = user.get_full_name() if hasattr(user, "get_full_name") else ""
    return full_name or getattr(user, "username", "")


def initials(name: str) -> str:
    parts = [part for part in (name or "").split() if part]
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


# ─── Səviyyə ────────────────────────────────────────────────────────────────


def effective_level(role, *, is_org_owner: bool = False) -> int:
    """Rolun RBAC-də FAKTİKİ səviyyəsi — `_highest_role_level()` ilə eyni hesab.

    `Role.level` təşkilat kataloqunun öz rəqəmidir və platforma səviyyəsindən
    AŞAĞI ola bilər: məktəb seed-ində «teacher» 50-dir, halbuki icazə qapıları
    müəllimi 60 sayır (`core.constants.ROLE_LEVELS` + `ProfileRole.LEVELS`
    aliasları). Qapı ilə ekranın eyni rəqəmi göstərməsi üçün şəxsə aid bütün
    səviyyə göstərişləri BU funksiyadan keçir; kataloq seçicilərində isə
    rolun öz `level` dəyəri qalır (mənbə fərqlidir, bax `role_options`).

    Hesab `apps/accounts/roles.py::_membership_effective_level` ilə eynidir.
    """
    name = ProfileRole.normalize_membership_role_name(getattr(role, "name", ""))
    raw_level = getattr(role, "level", 0) or 0
    aliases = ProfileRole.aliases_for_membership_role(name, level=raw_level, is_org_owner=is_org_owner)
    candidates = [raw_level, ROLE_LEVELS.get(name, 0)]
    candidates.extend(ROLE_LEVELS.get(alias, 0) for alias in aliases)
    candidates.extend(ProfileRole.LEVELS.get(alias, 0) for alias in aliases)
    return max(candidates, default=0)


# ─── Rol dərəcəsi (owner / admin) ───────────────────────────────────────────
#
# Rol təyinatı axını (`roles/_assignment_flow/_predicates.py`) eyni predikatları
# işlədir — çoxlu-rol axını ilə TƏK tərif paylaşsın deyə bura köçürüldü.


def is_owner_role(role) -> bool:
    if role is None:
        return False
    name = (getattr(role, "name", "") or "").strip().lower()
    return getattr(role, "level", 0) >= 100 or "owner" in name or name in {"rector", "director", "manager"}


def is_admin_role(role) -> bool:
    if role is None:
        return False
    name = (getattr(role, "name", "") or "").strip().lower()
    return (
        is_owner_role(role)
        or getattr(role, "level", 0) >= ProfileRole.LEVELS.get(ProfileRole.ORG_ADMIN, 80)
        or "admin" in name
    )


def is_org_wide_role(role) -> bool:
    """Rol bütün təşkilatı əhatə edirmi? (vahid-əhatəli aktor onu VERƏ BİLMƏZ)."""
    from core.constants import RoleScopeType

    return (getattr(role, "scope_type", "") or "") == RoleScopeType.ORGANIZATION


# ─── Kataloq ────────────────────────────────────────────────────────────────


def role_queryset(organization):
    from apps.organizations.models import Role

    return Role.objects.filter(organization=organization, is_active=True).order_by("-level", "name")


def assignable_roles(organization, *, actor_level, is_superadmin):
    """Aktorun VERƏ BİLDİYİ təşkilat rolları — səviyyə qapısı ilə.

    Qayda «Rol təyin et» ekranı ilə eynidir: superadmin xaric heç kim öz
    səviyyəsinə bərabər və ya ondan yuxarı rolu təyin edə bilməz. Müqayisə
    EFFEKTİV səviyyə ilə aparılır (bax `effective_level`) — əks halda məktəb
    seed-ində «teacher» (kataloq 50, faktiki 60) müəllimin öz siyahısında
    görünür, server isə onu rədd edirdi.
    """
    roles = list(role_queryset(organization))
    if is_superadmin:
        return roles
    return [role for role in roles if effective_level(role) < actor_level]


def roles_at_or_above(level, roles) -> list:
    """EFFEKTİV səviyyəsi `level`-dən aşağı OLMAYAN rolların id-ləri.

    Reyestr sorğularının SQL süzgəcində `Role.level` sütunundan istifadə etmək
    OLMAZ: kataloq rəqəmi ilə RBAC səviyyəsi fərqlidir (universitet seed-ində
    «Müəllim» 50/60, «Dekan» 80/90). Kataloq kiçikdir (onlarla sətir), ona görə
    effektiv səviyyə Python-da hesablanıb nəticə `IN (…)` kimi ötürülür — beləcə
    ekranda görünən dəst server qapısı ilə EYNİ olur.
    """
    return [role.id for role in roles if effective_level(role) >= level]


def users_holding_roles(organization, role_ids):
    """Verilmiş rollardan hər hansı birini AKTİV daşıyan istifadəçi id-ləri."""
    from apps.organizations.models import Membership

    return Membership.objects.filter(organization=organization, is_active=True, role_id__in=list(role_ids)).values(
        "user_id"
    )


def role_options(roles, *, placeholder: str = "") -> list[dict]:
    options = [{"value": "", "label": placeholder}] if placeholder else []
    options.extend({"value": str(role.id), "label": f"{role_label(role)} ({role.level})"} for role in roles)
    return options


# ─── Üzvlüklər ──────────────────────────────────────────────────────────────


def membership_queryset(organization, *, user_ids=None):
    from apps.organizations.models import Membership

    queryset = (
        Membership.objects.filter(organization=organization, is_active=True, role__is_active=True)
        .select_related("user", "role", "scope_unit")
        .order_by("-role__level", "role__name", "id")
    )
    if user_ids is not None:
        queryset = queryset.filter(user_id__in=list(user_ids))
    return queryset


def memberships_by_user(organization, *, user_ids=None) -> dict:
    """``{user_id: [Membership, …]}`` — səviyyəyə görə azalan sırada."""
    grouped: dict = {}
    for membership in membership_queryset(organization, user_ids=user_ids):
        grouped.setdefault(membership.user_id, []).append(membership)
    return grouped


def role_chip(membership) -> dict:
    """Cədvəl/çekmecə üçün bir rol nişanı."""
    role = membership.role
    scope_unit = membership.scope_unit
    return {
        "membership_id": str(membership.id),
        "role_id": str(role.id),
        "name": role.name,
        "label": role_label(role),
        "level": effective_level(role),
        "catalogue_level": role.level,
        "scope": scope_unit.name if scope_unit is not None else "",
        "is_primary": bool(membership.is_primary),
        "is_admin": is_admin_role(role),
        "is_owner": is_owner_role(role),
    }


def role_chips(memberships) -> list[dict]:
    return [role_chip(membership) for membership in memberships]


def primary_membership(memberships):
    """Ən yüksək səviyyəli aktiv üzvlük (``is_primary`` bayrağı etibarsız ola bilər)."""
    if not memberships:
        return None
    flagged = [membership for membership in memberships if membership.is_primary]
    pool = flagged or list(memberships)
    return max(pool, key=lambda membership: effective_level(membership.role))


def highest_role_level(memberships) -> int:
    return max((effective_level(membership.role) for membership in memberships), default=0)


# ─── Denormallaşdırılmış profil rolu ────────────────────────────────────────


def sync_profile_primary_role(user, organization) -> str:
    """``UserProfile.role``-u aktiv üzvlüklərin ƏN YÜKSƏYİNƏ görə yenilə.

    Köhnə enum sahəsi (``UserProfile.role``) geriyə uyğunluq üçün saxlanılır —
    naviqasiya və köhnə səthlər hələ ona baxır. Təşkilat rolu enum-da yoxdursa
    (``program_coordinator`` kimi) ``map_org_role_to_profile_role`` onu ən yaxın
    enum dəyərinə çevirir; ÜZVLÜK isə toxunulmadan qalır — mənbə odur.
    """
    from apps.accounts.models import UserProfile
    from apps.accounts.policies.roles import map_org_role_to_profile_role

    memberships = list(membership_queryset(organization, user_ids=[user.pk]))
    top = primary_membership(memberships)
    profile_role = map_org_role_to_profile_role(top.role) if top is not None else ProfileRole.MEMBER

    profile, _created = UserProfile.objects.get_or_create(user=user)
    if profile.role != profile_role:
        profile.role = profile_role
        profile.save(update_fields=["role", "updated_at"])
    return profile_role


__all__ = [
    "PAGE_SIZE",
    "ROLE_CHIP_PREVIEW",
    "assignable_roles",
    "display_name",
    "effective_level",
    "highest_role_level",
    "initials",
    "is_admin_role",
    "is_org_wide_role",
    "is_owner_role",
    "membership_queryset",
    "memberships_by_user",
    "primary_membership",
    "role_chip",
    "role_chips",
    "role_label",
    "role_options",
    "role_queryset",
    "roles_at_or_above",
    "sync_profile_primary_role",
    "users_holding_roles",
]
