"""«Müəllimlər» / «Tələbələr» kataloqunun İCAZƏ + SCOPE qapısı.

Bu modul kataloqun yeganə səlahiyyət mənbəyidir. Bütün servis funksiyaları və
view-lar data toxunmazdan ƏVVƏL buradan keçir; qapı **fail-closed**-dur.

İki sual QƏSDƏN AYRILIB (bax `apps/accounts/views/academic_records.py` şərhi):

* «Görməyə haqqın varmı?» → icazə açarı (`people.view_teachers` və s.).
  Açarlar `apps/organizations/permissions.py`-dakı ``people`` kateqoriyasındadır,
  yəni icazə redaktorundan İSTƏNİLƏN rola verilib-yığışdırıla bilir.
* «Nəyi görürsən?» → struktur scope-u (`apps.organizations.scoping`).

Scope üçün ``get_unit_scope`` DEYİL, ``get_permission_scope`` işlədilir. Fərq
kritikdir: ``get_unit_scope`` HƏR aktiv üzvlüyün ``scope_unit``-ini toplayır,
yəni «müəllimi kafedraya təyin et» əməliyyatı adi müəllimə kafedra alt-ağacı
verə bilir (2026-07-31 auditində məhz bu PII sızması tapılmışdı).
``get_permission_scope`` isə YALNIZ tələb olunan icazəni DAŞIYAN üzvlüyün
unitini sayır və scope_unit təyin edilməmiş UNIT rolu üçün **BOŞ** scope
qaytarır — bütün təşkilat DEYİL.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.organizations.scoping import EMPTY_SCOPE, ORG_WIDE_SCOPE, UnitScope, get_permission_scope
from core.permissions import has_permission

# ── İcazə açarları (kataloq: apps/organizations/permissions.py → "people") ────

PERM_VIEW_TEACHERS = "people.view_teachers"
PERM_VIEW_STUDENTS = "people.view_students"
PERM_VIEW_CONTACTS = "people.view_contacts"
PERM_VIEW_DEMOGRAPHICS = "people.view_demographics"
PERM_MANAGE_STATUS = "people.manage_status"
PERM_MANAGE_TEACHER_ROLE = "people.manage_teacher_role"

PEOPLE_PERMISSIONS = (
    PERM_VIEW_TEACHERS,
    PERM_VIEW_STUDENTS,
    PERM_VIEW_CONTACTS,
    PERM_VIEW_DEMOGRAPHICS,
    PERM_MANAGE_STATUS,
    PERM_MANAGE_TEACHER_ROLE,
)

#: Bölmə açarı → onu açan «baxış» icazəsi.
SECTION_VIEW_PERMISSION = {
    "people-teachers": PERM_VIEW_TEACHERS,
    "people-students": PERM_VIEW_STUDENTS,
}


@dataclass(frozen=True)
class PeopleActor:
    """Sorğu üçün həll olunmuş kataloq konteksti (icazə + təşkilat)."""

    user: object
    organization: object | None
    permissions: frozenset
    is_superadmin: bool

    def has(self, permission: str) -> bool:
        if self.is_superadmin:
            return True
        return has_permission(list(self.permissions), permission)

    @property
    def can_view_teachers(self) -> bool:
        return self.has(PERM_VIEW_TEACHERS)

    @property
    def can_view_students(self) -> bool:
        return self.has(PERM_VIEW_STUDENTS)

    @property
    def can_view_contacts(self) -> bool:
        return self.has(PERM_VIEW_CONTACTS)

    @property
    def can_view_demographics(self) -> bool:
        return self.has(PERM_VIEW_DEMOGRAPHICS)

    @property
    def can_manage_status(self) -> bool:
        return self.has(PERM_MANAGE_STATUS)

    @property
    def can_manage_teacher_role(self) -> bool:
        return self.has(PERM_MANAGE_TEACHER_ROLE)

    @property
    def granted_permissions(self) -> list:
        """Aktorun faktiki daşıdığı kataloq açarları — UI-a ötürülür."""
        return [perm for perm in PEOPLE_PERMISSIONS if self.has(perm)]

    def scope_for(self, permission: str, request=None) -> UnitScope:
        """İcazəni daşıyan üzvlüklərdən həll olunan struktur scope-u.

        İcazə ümumiyyətlə yoxdursa BOŞ scope — çağıran unutsa belə sorğu
        heç nə qaytarmır (ikiqat qapı).
        """
        if not self.has(permission):
            return EMPTY_SCOPE
        if self.is_superadmin:
            return ORG_WIDE_SCOPE
        if self.organization is None:
            return EMPTY_SCOPE
        return get_permission_scope(self.user, self.organization, permission, request=request)


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def resolve_actor(request) -> PeopleActor:
    """Sorğudan kataloq aktorunu qurur. Heç vaxt exception atmır (fail-closed)."""
    from apps.accounts.views._helpers.tenant import _get_active_organization

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return PeopleActor(user=None, organization=None, permissions=frozenset(), is_superadmin=False)

    organization = _get_active_organization(request)

    if _is_superadmin(user):
        return PeopleActor(
            user=user,
            organization=organization,
            permissions=frozenset({"*"}),
            is_superadmin=True,
        )

    if organization is None:
        # Təşkilat konteksti yoxdursa rol da yoxdur → kataloq bağlıdır.
        return PeopleActor(user=user, organization=None, permissions=frozenset(), is_superadmin=False)

    if getattr(organization, "owner_id", None) == getattr(user, "pk", None):
        return PeopleActor(user=user, organization=organization, permissions=frozenset({"*"}), is_superadmin=False)

    from apps.organizations.models import Membership

    memberships = Membership.objects.filter(
        user=user,
        organization=organization,
        is_active=True,
        role__organization=organization,
        role__is_active=True,
    ).values_list("role__permissions", flat=True)

    permissions: set = set()
    for role_permissions in memberships:
        for permission in role_permissions or []:
            # `grant:<perm>` delegasiya prefiksidir — icazəni AKTİV ETMİR.
            if not str(permission).startswith("grant:"):
                permissions.add(str(permission))

    return PeopleActor(
        user=user,
        organization=organization,
        permissions=frozenset(permissions),
        is_superadmin=False,
    )


__all__ = [
    "PEOPLE_PERMISSIONS",
    "PERM_MANAGE_STATUS",
    "PERM_MANAGE_TEACHER_ROLE",
    "PERM_VIEW_CONTACTS",
    "PERM_VIEW_DEMOGRAPHICS",
    "PERM_VIEW_STUDENTS",
    "PERM_VIEW_TEACHERS",
    "SECTION_VIEW_PERMISSION",
    "PeopleActor",
    "resolve_actor",
]
