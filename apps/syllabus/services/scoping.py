"""Aktor konteksti və FAIL-CLOSED əhatə (scope) yoxlaması.

Kafedra müdiri YALNIZ öz kafedrasının sillabuslarını görməli və təsdiqləməlidir.
Əhatə ``Membership.scope_unit`` üzərindən hesablanır — mövcud
:mod:`apps.organizations.scoping` servisi ilə, YENİ scope məntiqi icad edilmir.

⚠️ FAIL-CLOSED qayda (əvvəlki bloker): scope-u OLMAYAN istifadəçiyə bütün
təşkilat AÇILMIR. Ona görə burada həmişə ``permission=...`` ilə çağırılır —
``get_permission_scope`` bu rejimdə struktur əhatəsi tapılmayanda ``False``
qaytarır, «scope yoxdursa hər şey görünsün» geriyə-uyğunluq davranışı yalnız
permission-suz köhnə çağırışlara aiddir.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.organizations.scoping import get_permission_scope, user_scope_covers_unit

from ..constants import PERM_VIEW


@dataclass(frozen=True)
class SyllabusActor:
    """Sillabus əməliyyatını icra edən şəxsin həll olunmuş konteksti."""

    user: object
    organization: object
    permissions: tuple
    is_superadmin: bool = False

    @property
    def user_id(self):
        return getattr(self.user, "pk", None)

    def has(self, permission: str) -> bool:
        from core.permissions import has_permission

        return self.is_superadmin or has_permission(list(self.permissions), permission)

    def covers_unit(self, unit_id, permission: str) -> bool:
        """Aktorun struktur əhatəsi verilmiş kafedranı tuturmu (fail-closed)."""
        if self.is_superadmin:
            return True
        return bool(user_scope_covers_unit(self.user, self.organization, unit_id, permission=permission))

    def scope_for(self, permission: str):
        """Verilmiş icazə üçün ``UnitScope`` (siyahı sorğularını daraltmaq üçün)."""
        if self.is_superadmin:
            from apps.organizations.scoping import ORG_WIDE_SCOPE

            return ORG_WIDE_SCOPE
        return get_permission_scope(self.user, self.organization, permission)


def resolve_actor(user, organization, *, request=None) -> SyllabusActor:
    """Aktiv üzvlüklərdən aktorun icazə dəstini toplayır.

    ``request`` verilibsə middleware-in hesabladığı ``org_permissions`` işlədilir
    (əlavə sorğu yoxdur); əks halda aktiv üzvlüklərdən yenidən yığılır.
    """
    from core.permissions import is_superadmin_user

    permissions: list = []
    if request is not None and getattr(request, "org_permissions", None):
        permissions = list(request.org_permissions)
    elif user is not None and getattr(user, "is_authenticated", False):
        from apps.organizations.services import get_active_memberships

        for membership in get_active_memberships(user, organization):
            role = membership.role
            if role and role.is_active:
                permissions.extend(role.permissions or [])

    return SyllabusActor(
        user=user,
        organization=organization,
        permissions=tuple(dict.fromkeys(permissions)),
        is_superadmin=is_superadmin_user(user),
    )


def is_author(actor: SyllabusActor, syllabus) -> bool:
    """Aktor bu sillabusun müəllifidir(mi) — müəllif və ya açılışın müəllimi."""
    user_id = actor.user_id
    if user_id is None:
        return False
    if syllabus.author_id == user_id:
        return True
    offering = getattr(syllabus, "offering", None)
    return bool(offering and offering.instructor_id == user_id)


def can_view(actor: SyllabusActor, syllabus) -> bool:
    """Baxış hüququ: müəllif HƏMİŞƏ, digərləri icazə + kafedra əhatəsi ilə."""
    if is_author(actor, syllabus):
        return True
    if not actor.has(PERM_VIEW):
        return False
    return actor.covers_unit(syllabus.chair_unit_id, PERM_VIEW)


__all__ = ["SyllabusActor", "can_view", "is_author", "resolve_actor"]
