"""Aktor konteksti və FAIL-CLOSED əhatə yoxlaması (sillabus naxışı).

Kafedra müdiri YALNIZ öz kafedrasının tapşırığını görür və bölür; müəllim
yalnız ÖZ bölgü sətirlərini görür. Əhatə ``Membership.scope_unit`` üzərindən
mövcud :mod:`apps.organizations.scoping` servisi ilə hesablanır — yeni scope
məntiqi icad edilmir.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.organizations.scoping import get_permission_scope, user_scope_covers_unit

from ..constants import PERM_DISTRIBUTE, PERM_MANAGE, PERM_REPORT, PERM_VIEW


class WorkloadDenied(Exception):
    """İcazə/əhatə pozuntusu — view qatı bunu 403-ə çevirir."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(code, message)
        self.code = code
        self.message = message or code

    def __str__(self):
        return self.message


@dataclass(frozen=True)
class WorkloadActor:
    """Dərs yükü əməliyyatını icra edən şəxsin həll olunmuş konteksti."""

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
        if unit_id is None:
            return False
        return bool(user_scope_covers_unit(self.user, self.organization, unit_id, permission=permission))

    def scope_for(self, permission: str):
        if self.is_superadmin:
            from apps.organizations.scoping import ORG_WIDE_SCOPE

            return ORG_WIDE_SCOPE
        return get_permission_scope(self.user, self.organization, permission)


def resolve_actor(user, organization, *, request=None) -> WorkloadActor:
    """Aktiv üzvlüklərdən (və ya middleware kontekstindən) icazə dəstini toplayır."""
    from core.permissions import is_superadmin_user

    permissions: list = []
    if request is not None and getattr(request, "org_permissions", None):
        permissions = list(request.org_permissions)
    elif user is not None and getattr(user, "is_authenticated", False) and organization is not None:
        from apps.organizations.services import get_active_memberships

        for membership in get_active_memberships(user, organization):
            role = membership.role
            if role and role.is_active:
                permissions.extend(role.permissions or [])

    return WorkloadActor(
        user=user,
        organization=organization,
        permissions=tuple(dict.fromkeys(permissions)),
        is_superadmin=is_superadmin_user(user),
    )


# ── Qapılar ─────────────────────────────────────────────────────────────────


def can_view_task(actor: WorkloadActor, task) -> bool:
    if not actor.has(PERM_VIEW):
        return False
    return actor.covers_unit(task.chair_id, PERM_VIEW)


def can_manage_chair(actor: WorkloadActor, chair_id) -> bool:
    """Tapşırıq yaratmaq/sətir redaktə etmək (kafedra müdiri, RİM, rektorluq)."""
    if not actor.has(PERM_MANAGE):
        return False
    return actor.covers_unit(chair_id, PERM_MANAGE)


def can_distribute_chair(actor: WorkloadActor, chair_id) -> bool:
    if not actor.has(PERM_DISTRIBUTE):
        return False
    return actor.covers_unit(chair_id, PERM_DISTRIBUTE)


def can_report(actor: WorkloadActor) -> bool:
    return actor.has(PERM_REPORT)


def ensure_can_manage(actor: WorkloadActor, chair_id) -> None:
    if not can_manage_chair(actor, chair_id):
        raise WorkloadDenied("workload.manage_denied", "Bu kafedranın tapşırığını idarə etmək səlahiyyətiniz yoxdur.")


def ensure_can_distribute(actor: WorkloadActor, chair_id) -> None:
    if not can_distribute_chair(actor, chair_id):
        raise WorkloadDenied("workload.distribute_denied", "Bu kafedranın yükünü bölmək səlahiyyətiniz yoxdur.")


def ensure_can_view(actor: WorkloadActor, task) -> None:
    if not can_view_task(actor, task):
        raise WorkloadDenied("workload.view_denied", "Bu tapşırığa baxış səlahiyyətiniz yoxdur.")


def manageable_chairs(actor: WorkloadActor, *, permission: str = PERM_MANAGE):
    """Aktorun idarə edə bildiyi kafedra ``OrgUnit`` queryset-i (fail-closed)."""
    from django.apps import apps as django_apps

    from core.constants import OrgUnitType

    if not actor.has(permission):
        return _empty_units()
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    base = OrgUnit.objects.filter(
        organization=actor.organization,
        is_active=True,
        unit_type__in=(OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT),
    )
    scope = actor.scope_for(permission)
    if scope.is_org_wide:
        return base.order_by("name")
    if not scope.has_structure_access:
        return _empty_units()
    return base.filter(scope.unit_subtree_q()).order_by("name")


def _empty_units():
    from django.apps import apps as django_apps

    return django_apps.get_model("organizations", "OrgUnit").objects.none()


__all__ = [
    "PERM_REPORT",
    "WorkloadActor",
    "WorkloadDenied",
    "can_distribute_chair",
    "can_manage_chair",
    "can_report",
    "can_view_task",
    "ensure_can_distribute",
    "ensure_can_manage",
    "ensure_can_view",
    "manageable_chairs",
    "resolve_actor",
]
