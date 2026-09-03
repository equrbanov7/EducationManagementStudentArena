"""RİM mərkəzinin TƏHLÜKƏSİZLİK QATI — kim kimi idarə edə bilər.

Bu modul RİM-in yeganə icazə qapısıdır. Bütün view-lar və servislər hədəfə
toxunmazdan ƏVVƏL buradan keçir; qapı **fail-closed**-dur — rol, üzvlük və ya
icazə tanınmırsa əməliyyat rədd olunur.

Qaydalar (dəyişdirməzdən əvvəl `apps/accounts/tests/test_rim_center.py`-a bax):

1. Aktorun AKTİV təşkilat kontekstində AKTİV üzvlüyü olmalıdır. Üzvlük
   deaktivdirsə rol həll olunmur → icazə yoxdur (bax MEMORY: «role needs
   active membership»).
2. Tələb olunan `user.*` icazəsi aktorun rol icazələrində olmalıdır.
   Superadmin (`is_superuser`) istisnadır.
3. **Superuser hesab HEÇ VAXT hədəf ola bilməz** — hətta başqa superadmin üçün də.
   Bu, platforma səviyyəsində sındırılmaz qayda: superadmin hesabları yalnız
   Django admin / server tərəfindən idarə olunur.
4. Aktor ÖZ hesabını RİM vasitəsilə idarə edə bilməz (blok/silmə/parol/redaktə).
   Öz parolunu «Parolu dəyiş» bölməsindən dəyişir.
5. **Ciddi iyerarxiya**: hədəfin təşkilatdakı MAKSİMUM rol səviyyəsi aktorunkundan
   AŞAĞI olmalıdır (`<`, bərabər DEYİL). Yəni eyni səviyyəli iki İKT rəhbəri
   bir-birini bloklaya bilməz. Superadmin bu qaydadan azaddır.
6. Təşkilat SAHİBİ (owner) yalnız superadmin tərəfindən idarə oluna bilər.
7. Hədəf aktorun aktiv təşkilatının üzvü olmalıdır (tenant izolyasiyası).
   Superadmin cross-org işləyə bilər.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db.models import Max, Q

from core.permissions import has_permission

User = get_user_model()

# RİM-in bütün icazə açarları (bax `apps/organizations/permissions.py` «users»).
PERM_SEARCH = "user.search"
PERM_CREDENTIALS = "user.credentials"
PERM_BLOCK = "user.block"
PERM_SOFT_DELETE = "user.soft_delete"
PERM_EDIT = "user.edit"

RIM_PERMISSIONS = (
    PERM_SEARCH,
    PERM_CREDENTIALS,
    PERM_BLOCK,
    PERM_SOFT_DELETE,
    PERM_EDIT,
)

#: Aktorun səviyyəsi bu həddə çatırsa iyerarxiya/tenant filtrləri tətbiq olunmur.
SUPERADMIN_LEVEL = 999


class RimAccessError(Exception):
    """RİM əməliyyatı icazə/iyerarxiya qapısından keçmədi.

    ``reason_code`` maşın-oxunaqlı (audit + JSON cavab), ``message`` isə
    istifadəçiyə göstərilən AZ mətndir.
    """

    # Bütün arqumentlər `super().__init__()`-ə ötürülür ki, exception `pickle` /
    # `copy.copy()` ilə düzgün bərpa olunsun (flake8-bugbear B042).
    def __init__(self, reason_code: str, message: str, status: int = 403):
        super().__init__(reason_code, message, status)
        self.reason_code = reason_code
        self.message = message
        self.status = status

    def __str__(self):
        # `args` üç elementlidir (yuxarıdakı B042 qeydinə bax), amma log/debug
        # çıxışında yalnız səbəb kodu görünməlidir.
        return self.reason_code


@dataclass
class RimActor:
    """Aktorun bu sorğu üçün həll olunmuş RİM konteksti."""

    user: object
    organization: object | None
    level: int
    is_superadmin: bool
    permissions: set = field(default_factory=set)

    def has(self, permission: str) -> bool:
        """Aktorun konkret RİM icazəsi varmı (superadmin həmişə var)."""
        if self.is_superadmin:
            return True
        return has_permission(list(self.permissions), permission)

    @property
    def rim_permissions(self) -> list:
        """Aktorun faktiki daşıdığı RİM açarları — UI-da göstərmək üçün."""
        return [perm for perm in RIM_PERMISSIONS if self.has(perm)]

    @property
    def can_use_rim(self) -> bool:
        return bool(self.rim_permissions)


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def resolve_actor(request) -> RimActor:
    """Sorğudan RİM aktorunu qurur. Heç vaxt exception atmır — fail-closed boş aktor."""
    from apps.accounts.views._helpers.tenant import _get_active_organization

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return RimActor(user=None, organization=None, level=0, is_superadmin=False)

    organization = _get_active_organization(request)

    if _is_superadmin(user):
        return RimActor(
            user=user,
            organization=organization,
            level=SUPERADMIN_LEVEL,
            is_superadmin=True,
            permissions={"*"},
        )

    if organization is None:
        # Təşkilat konteksti yoxdursa rol da yoxdur → RİM bağlıdır.
        return RimActor(user=user, organization=None, level=0, is_superadmin=False)

    from apps.organizations.models import Membership

    memberships = list(
        Membership.objects.filter(
            user=user,
            organization=organization,
            is_active=True,
            role__is_active=True,
        ).select_related("role")
    )

    permissions: set = set()
    levels = [0]
    for membership in memberships:
        levels.append(int(getattr(membership.role, "level", 0) or 0))
        for permission in membership.role.permissions or []:
            # `grant:<perm>` delegasiya prefiksidir — icazəni AKTİV ETMİR.
            if not str(permission).startswith("grant:"):
                permissions.add(permission)

    level = max(levels)
    if getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        # Sahib öz təşkilatında ən yüksək səviyyədədir (üzvlüyü olmasa belə).
        from core.roles import ProfileRole

        level = max(level, ProfileRole.LEVELS.get(ProfileRole.ORG_OWNER, 90))
        permissions.add("*")

    return RimActor(
        user=user,
        organization=organization,
        level=level,
        is_superadmin=False,
        permissions=permissions,
    )


def require_permission(actor: RimActor, permission: str) -> None:
    """Aktorda icazə yoxdursa ``RimAccessError`` atır."""
    if not actor.has(permission):
        raise RimAccessError(
            "permission_denied",
            "Bu əməliyyat üçün icazəniz yoxdur.",
        )


def _is_soft_deleted(user) -> bool:
    profile = getattr(user, "profile", None)
    return bool(profile is not None and getattr(profile, "is_deleted", False))


def target_level(target_user, organization) -> int:
    """Hədəfin təşkilatdakı maksimum rol səviyyəsi.

    SİLİNMİŞ hesab üçün DEAKTİV üzvlüklər də sayılır. Səbəb: `soft_delete_account`
    bütün üzvlükləri deaktiv edir, yəni silinmiş rektorun aktiv rolu qalmır və
    yalnız aktiv üzvlüklərə baxsaydıq onun səviyyəsi 0 görünərdi — istənilən
    kiçik operator onu bərpa edə bilərdi. Silinmə iyerarxiyanı sıfırlamamalıdır.
    """
    if organization is None:
        return 0

    from apps.organizations.models import Membership

    memberships = Membership.objects.filter(user=target_user, organization=organization)
    if not _is_soft_deleted(target_user):
        memberships = memberships.filter(is_active=True, role__is_active=True)

    aggregate = memberships.aggregate(top=Max("role__level"))
    level = int(aggregate.get("top") or 0)

    if getattr(organization, "owner_id", None) == getattr(target_user, "pk", None):
        from core.roles import ProfileRole

        level = max(level, ProfileRole.LEVELS.get(ProfileRole.ORG_OWNER, 90))
    return level


def assert_can_manage(actor: RimActor, target_user) -> None:
    """Aktorun hədəfi idarə edə biləcəyini yoxlayır; yoxsa ``RimAccessError``.

    Yuxarıdakı 3–7 qaydaları burada tətbiq olunur (1–2 `require_permission`-da).
    """
    if target_user is None:
        raise RimAccessError("target_not_found", "İstifadəçi tapılmadı.", status=404)

    # (3) Superuser hesab heç vaxt hədəf ola bilməz.
    if _is_superadmin(target_user):
        raise RimAccessError(
            "target_is_superadmin",
            "Superadmin hesabı RİM mərkəzindən idarə oluna bilməz.",
        )

    # (4) Öz hesabı.
    if getattr(actor.user, "pk", None) == getattr(target_user, "pk", None):
        raise RimAccessError(
            "target_is_self",
            "Öz hesabınızı bu bölmədən idarə edə bilməzsiniz.",
        )

    if actor.is_superadmin:
        return

    organization = actor.organization
    if organization is None:
        raise RimAccessError("no_organization_context", "Aktiv təşkilat konteksti yoxdur.")

    # (7) Tenant izolyasiyası — hədəf aktorun təşkilatının üzvü olmalıdır.
    #
    # SİLİNMİŞ hesab üçün üzvlüyün DEAKTİV olması kifayətdir: soft-delete bütün
    # üzvlükləri söndürür və `profile.organization`-u NULL edir, yəni yalnız
    # aktiv üzvlüyə baxsaydıq silinmiş hesabı BƏRPA ETMƏK mümkün olmazdı
    # (yalnız superadmin bacarardı). Üzvlük SƏTİRLƏRİ isə silinmir — org linki
    # orada qalır və tenant sərhədini qorumaq üçün kifayət edir.
    from apps.organizations.models import Membership

    membership_filter = Membership.objects.filter(user=target_user, organization=organization)
    if not _is_soft_deleted(target_user):
        membership_filter = membership_filter.filter(is_active=True)
    is_member = membership_filter.exists()
    if not is_member and getattr(organization, "owner_id", None) != getattr(target_user, "pk", None):
        raise RimAccessError(
            "target_outside_organization",
            "İstifadəçi sizin təşkilatınızın üzvü deyil.",
            status=404,
        )

    # (6) Təşkilat sahibi.
    if getattr(organization, "owner_id", None) == getattr(target_user, "pk", None):
        raise RimAccessError(
            "target_is_owner",
            "Təşkilat sahibinin hesabı RİM mərkəzindən idarə oluna bilməz.",
        )

    # (5) Ciddi iyerarxiya.
    if target_level(target_user, organization) >= actor.level:
        raise RimAccessError(
            "target_rank_too_high",
            "Özünüzlə eyni və ya daha yüksək səlahiyyətli hesabı idarə edə bilməzsiniz.",
        )


def manageable_users_queryset(actor: RimActor):
    """Aktorun RİM-də görə/idarə edə biləcəyi istifadəçilərin baza queryset-i.

    Silinmiş (soft-deleted) hesablar DA daxildir — bərpa əməliyyatı üçün lazımdır;
    `is_active=False` da daxildir (bloklanmışlar). Filtrləmə `search.py`-dədir.
    """
    if actor.user is None:
        return User.objects.none()

    queryset = User.objects.select_related("profile", "profile__organization").exclude(is_superuser=True)
    queryset = queryset.exclude(pk=getattr(actor.user, "pk", None))

    if actor.is_superadmin:
        return queryset.distinct()

    organization = actor.organization
    if organization is None:
        return User.objects.none()

    # Aktiv üzv VƏ YA bu təşkilatda üzvlük izi olan silinmiş hesab (bərpa üçün).
    queryset = queryset.filter(
        Q(memberships__organization=organization, memberships__is_active=True)
        | Q(memberships__organization=organization, profile__is_deleted=True)
    )

    owner_id = getattr(organization, "owner_id", None)
    if owner_id:
        queryset = queryset.exclude(pk=owner_id)

    # Ciddi iyerarxiya queryset səviyyəsində — `target_level()` ilə eyni qayda:
    # aktiv hesab üçün AKTİV üzvlüklər, silinmiş hesab üçün BÜTÜN üzvlüklər.
    queryset = queryset.annotate(
        _rim_active_level=Max(
            "memberships__role__level",
            filter=Q(memberships__organization=organization, memberships__is_active=True),
        ),
        _rim_any_level=Max(
            "memberships__role__level",
            filter=Q(memberships__organization=organization),
        ),
    ).filter(
        Q(profile__is_deleted=True, _rim_any_level__lt=actor.level)
        | Q(profile__is_deleted=True, _rim_any_level__isnull=True)
        | Q(_rim_active_level__lt=actor.level)
        | Q(_rim_active_level__isnull=True, profile__is_deleted=False)
    )

    return queryset.distinct()


__all__ = [
    "PERM_BLOCK",
    "PERM_CREDENTIALS",
    "PERM_EDIT",
    "PERM_SEARCH",
    "PERM_SOFT_DELETE",
    "RIM_PERMISSIONS",
    "RimAccessError",
    "RimActor",
    "assert_can_manage",
    "manageable_users_queryset",
    "require_permission",
    "resolve_actor",
    "target_level",
]
