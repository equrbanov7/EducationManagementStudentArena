"""Tələbə hesablarının şəxsi məlumatı — kim görür (QA-2 F-03, 2026-10-17). TƏK MƏNBƏ.

HR (heyət idxalı) `member.view` / `member.edit` / `role.assign` / `user.search` / `user.edit` daşıyır, amma
tələbə kataloqu ona bağlıdır (rol auditi B6). Bu açarlar heyət üçündür: TƏLƏBƏ hesabları (ad, istifadəçi adı,
şəxsi e-poçt, rol dəyişimi) yalnız tələbə tərəfi açarlarından birini daşıyan aktora görünür. Rol ADI
yoxlanmır, yalnız açar (``core.permissions.has_permission`` — `*` / `prefix.*` də sayılır).

İstifadə edənlər: RİM mərkəzi (`apps.accounts.services.rim.policy`), «Struktur üzvləri» reyestri + üzv kartı +
CSV ixracı + ümumi baxış (`structure_views.members_base.resolve_members_access`), «Rol təyin et».

MODUL SƏRHƏDİ: ``apps.accounts`` statik import EDİLMİR — ``UserProfile`` ``django_apps.get_model`` ilə.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db.models import Exists, OuterRef, Q

from core.permissions import has_permission

#: Tələbə tərəfi açarları. `user.credentials` / `account.password_reset` — hesab operatoru (parolu tələbəyə də
#: verir); `student.records_view` — Tədris şöbəsi əməkdaşı (akademik qeydlər).
STUDENT_ACCOUNT_PERMISSIONS = (
    "people.view_students",
    "student.registry_view",
    "student.records_view",
    "user.credentials",
    "account.password_reset",
)
#: Tələbə ailəsi rolları; ``member`` (doldurucu) neytraldır.
STUDENT_ROLE_NAMES = ("student", "lead_student", "alumni")
NEUTRAL_ROLE_NAMES = ("member",)


def holds_student_key(permissions) -> bool:
    """İcazə siyahısında tələbə tərəfi açarı varmı."""
    permission_list = list(permissions or [])
    return any(has_permission(permission_list, key) for key in STUDENT_ACCOUNT_PERMISSIONS)


def request_holds_student_key(request) -> bool:
    """Sorğunun aktoru (aktiv təşkilat icazələri) tələbə tərəfi açarı daşıyırmı; superadmin və sahib həmişə."""
    user = getattr(request, "user", None)
    if getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False):
        return True
    organization = getattr(request, "organization", None)
    if organization is not None and getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return True
    return holds_student_key(getattr(request, "org_permissions", None))


def student_only_q(organization, *, user_ref: str = "pk") -> Q:
    """Təşkilatda YALNIZ tələbə ailəsi rolu olan hesab (EXISTS — JOIN dublikatı yoxdur).

    ``user_ref`` — xarici sorğuda istifadəçi id-si sahəsi: ``User`` üçün ``"pk"``, ``Membership`` üçün
    ``"user_id"``. Aktiv hesab üçün AKTİV üzvlüklər, silinmiş hesab üçün BÜTÜN üzvlüklər sayılır — silinmiş
    tələbə də tələbə qalır. Həm tələbə, həm heyət olan hesab (magistrant müəllim) heyətdir.
    """
    membership_model = django_apps.get_model("organizations", "Membership")
    profile_model = django_apps.get_model("accounts", "UserProfile")

    def _student_only(memberships):
        return Exists(memberships.filter(role__name__in=STUDENT_ROLE_NAMES)) & ~Exists(
            memberships.exclude(role__name__in=(*STUDENT_ROLE_NAMES, *NEUTRAL_ROLE_NAMES))
        )

    any_membership = membership_model.objects.filter(user_id=OuterRef(user_ref), organization=organization)
    active = _student_only(any_membership.filter(is_active=True))
    # EXISTS (LEFT JOIN `profile` sahəsi deyil): `exclude()` altında NULL profil sətri itməsin.
    is_deleted = Exists(profile_model.objects.filter(user_id=OuterRef(user_ref), is_deleted=True))
    return Q(active) | (Q(is_deleted) & _student_only(any_membership))


__all__ = [
    "NEUTRAL_ROLE_NAMES",
    "STUDENT_ACCOUNT_PERMISSIONS",
    "STUDENT_ROLE_NAMES",
    "holds_student_key",
    "request_holds_student_key",
    "student_only_q",
]
