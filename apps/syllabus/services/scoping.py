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

from apps.organizations.public import get_permission_scope, user_scope_covers_unit

from ..constants import PERM_APPROVE, PERM_VIEW


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

    def covers_chair_unit(self, unit_id, permission: str) -> bool:
        """QƏRAR əhatəsi: bağ KAFEDRA SƏVİYYƏSİNDƏ olmalıdır (sahibin qərarı).

        ``covers_unit`` alt-ağac yoxlamasıdır — dekanın fakültə scope-u
        altındakı bütün kafedraları örtür.  Təsdiq/düzəliş/rədd üçün bu AZ
        DEYİL, ÇOXDUR: qərar kafedra müdirinindir.  Org-wide əhatə (rektor,
        prorektor, RİM, superadmin) override kimi saxlanılır — hər əməl
        onsuz da audit jurnalına düşür.
        """
        if self.is_superadmin:
            return True
        scope = self.scope_for(permission)
        if scope.is_org_wide:
            return True
        if not scope.is_unit_scoped or unit_id is None:
            return False
        from .units import chair_level_scope_covers

        return chair_level_scope_covers(scope.unit_ids, unit_id)

    def scope_for(self, permission: str):
        """Verilmiş icazə üçün ``UnitScope`` (siyahı sorğularını daraltmaq üçün)."""
        if self.is_superadmin:
            from apps.organizations.public import ORG_WIDE_SCOPE

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
        from apps.organizations.public import get_active_memberships

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


def _author_users(syllabus) -> list:
    """Sillabusun müəllif sayılan istifadəçiləri (``is_author`` ilə eyni qayda)."""
    users = [getattr(syllabus, "author", None)]
    offering = getattr(syllabus, "offering", None)
    if offering is not None:
        users.append(getattr(offering, "instructor", None))
    seen, result = set(), []
    for user in users:
        if user is not None and user.pk not in seen:
            seen.add(user.pk)
            result.append(user)
    return result


def is_self_authored_by_decider(syllabus, permission: str = PERM_APPROVE) -> bool:
    """Audit 2026-09-28 SYL-1: müəllif bu kafedrada ÖZÜ qərarvericidirmi.

    Belə sillabusda müəllif qərar verə bilmir (``forbid_author``), ona görə
    qərar növbəti pilləyə — fakültə səviyyəli açar sahibinə (dekan) və ya
    org-wide aktora — keçir.  Fail-closed: müəllif tapılmasa ``False``.
    """
    organization = getattr(syllabus, "organization", None)
    for user in _author_users(syllabus):
        author_actor = resolve_actor(user, organization)
        if author_actor.has(permission) and author_actor.covers_chair_unit(syllabus.chair_unit_id, permission):
            return True
    return False


def has_escalated_decision_scope(actor: SyllabusActor, permission: str = PERM_APPROVE) -> bool:
    """Qərar açarı olan, amma kafedra səviyyəli olmayan (fakültə) əhatə.

    Audit 2026-09-28 SYL-1: belə aktor YALNIZ müəllifi kafedra qərarvericisi
    olan sillabuslarda qərar verir — UI düymələri versiya üzrə
    ``available_actions`` ilə daraldılır.
    """
    if actor.is_superadmin or not actor.has(permission):
        return False
    scope = actor.scope_for(permission)
    return bool(scope.is_unit_scoped and not has_decision_scope(actor, permission))


def can_view(actor: SyllabusActor, syllabus) -> bool:
    """Baxış hüququ: müəllif HƏMİŞƏ, digərləri icazə + kafedra əhatəsi ilə."""
    if is_author(actor, syllabus):
        return True
    if not actor.has(PERM_VIEW):
        return False
    return actor.covers_unit(syllabus.chair_unit_id, PERM_VIEW)


def has_decision_scope(actor: SyllabusActor, permission: str = PERM_APPROVE) -> bool:
    """Aktorun ÜMUMİYYƏTLƏ qərar əhatəsi varmı — UI düymələri üçün.

    Sətir-sətir ``covers_chair_unit`` per-sillabus cavab verir; növbə ekranı isə
    düymələri BİR DƏFƏ göstərib-gizlətməlidir.  Burada yalnız «bu aktorun
    kafedra səviyyəli (və ya org-wide) əhatəsi varmı» sualına baxılır.
    """
    if actor.is_superadmin:
        return True
    if not actor.has(permission):
        return False
    scope = actor.scope_for(permission)
    if scope.is_org_wide:
        return True
    if not scope.is_unit_scoped:
        return False
    from .units import has_chair_level_unit

    return has_chair_level_unit(actor.organization, scope.unit_ids)


__all__ = [
    "SyllabusActor",
    "can_view",
    "has_decision_scope",
    "has_escalated_decision_scope",
    "is_author",
    "is_self_authored_by_decider",
    "resolve_actor",
]
