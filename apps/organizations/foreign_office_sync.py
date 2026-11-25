"""«Əcnəbi tələbələrlə iş şöbəsi» — rol + əhatə sinxronu (sahib 2026-11-25).

Qayda (``default_roles_foreign_office``):

1. Şöbə rolları təşkilatda yoxdursa şablondan yaradılır; varsa çatışmayan açarlar əlavə olunur (``*`` toxunulmur).
2. Şöbə bölməsindəki (adında «əcnəbi», akademik olmayan) AKTİV üzvlüklər: ``admin_unit_head`` → şöbə müdiri rolu,
   ``member`` → şöbə əməkdaşı rolu. Köhnə üzvlük QALIR (üzv reyestrində şöbəsi görünsün).
3. Hər belə şəxsə hər AKTİV əcnəbi QRUPU (adında «əcnəbi», ``group`` tipli) üçün ayrıca UNIT üzvlüyü
   (``scope_unit`` = qrup). Mövcud sətir təkrar yaradılmır; passiv sətir yenidən aktivləşdirilir.

Heç nə silinmir. İdempotentdir — yeni əcnəbi qrupu açılandan sonra təkrar işlədilir. Miqrasiya ``0087`` eyni qaydanı
tarixi modellərlə tətbiq edir (paritet testi: ``tests/test_foreign_students_office_2026_11_25``).
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps

from .default_roles_foreign_office import DEPARTMENT_ROLE_MAP, FOREIGN_STUDENTS_ROLES, is_foreign_office_unit

_AUDIT_RESOURCE = "organizations.foreign_office_scope"


def ensure_roles(organization) -> dict:
    Role = django_apps.get_model("organizations", "Role")
    roles = {}
    for spec in FOREIGN_STUDENTS_ROLES:
        role = Role.objects.filter(organization=organization, name=spec["name"]).first()
        if role is None:
            role = Role.objects.create(
                organization=organization,
                name=spec["name"],
                display_name=spec["display_name"],
                description=spec["description"],
                level=spec["level"],
                scope_type=spec["scope_type"],
                permissions=list(spec["permissions"]) + ["application.create"],
                is_system=True,
                is_active=True,
            )
        else:
            permissions = list(role.permissions or [])
            missing = [key for key in spec["permissions"] if key not in permissions]
            if missing and "*" not in permissions:
                role.permissions = permissions + missing
                role.save(update_fields=["permissions"])
        roles[spec["name"]] = role
    return roles


def foreign_groups(organization) -> list:
    """Aktiv əcnəbi qrupları — açıq «Qrup növü» (``group_kind``), yoxdursa ad qaydası."""
    from .group_kind import is_foreign

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return [
        unit
        for unit in OrgUnit.objects.filter(organization=organization, unit_type="group", is_active=True).only(
            "id", "name", "unit_type", "settings"
        )
        if is_foreign(unit)
    ]


def sync_for_group(organization, unit, *, actor=None) -> int:
    """Qrup yadda saxlananda: əcnəbi qrupudursa şöbəyə əhatə verilir (idempotent; başqa qrupa toxunmur)."""
    from .group_kind import is_foreign

    if unit is None or not unit.is_active or not is_foreign(unit):
        return 0
    _counts, wanted = plan(organization)
    return apply(organization, [item for item in wanted if item[2].pk == unit.pk], actor=actor)


def office_members(organization) -> list:
    """``[(user_id, target_role_name)]`` — şöbə bölməsindəki aktiv üzvlər (təkrarsız, müdir üstün)."""
    Membership = django_apps.get_model("organizations", "Membership")
    found: dict = {}
    rows = Membership.objects.filter(
        organization=organization,
        is_active=True,
        role__name__in=list(DEPARTMENT_ROLE_MAP),
        scope_unit__isnull=False,
        scope_unit__is_active=True,
    ).select_related("role", "scope_unit")
    for membership in rows:
        unit = membership.scope_unit
        if not is_foreign_office_unit(unit.name, unit.unit_type):
            continue
        target = DEPARTMENT_ROLE_MAP[membership.role.name]
        if found.get(membership.user_id) == DEPARTMENT_ROLE_MAP["admin_unit_head"]:
            continue
        found[membership.user_id] = target
    return sorted(found.items())


def plan(organization) -> tuple[Counter, list]:
    """``(counts, wanted)`` — ``wanted``: ``[(user_id, role_name, group)]`` hələ AKTİV olmayan üzvlüklər."""
    Membership = django_apps.get_model("organizations", "Membership")
    counts: Counter = Counter()
    groups = foreign_groups(organization)
    members = office_members(organization)
    counts["groups"] = len(groups)
    counts["people"] = len(members)
    existing = {
        (row.user_id, row.role.name, row.scope_unit_id): row.is_active
        for row in Membership.objects.filter(
            organization=organization,
            role__name__in=list(DEPARTMENT_ROLE_MAP.values()),
            scope_unit_id__in=[group.pk for group in groups],
        ).select_related("role")
    }
    wanted = []
    for user_id, role_name in members:
        for group in groups:
            state = existing.get((user_id, role_name, group.pk))
            if state is True:
                counts["already"] += 1
                continue
            counts["reactivate" if state is False else "create"] += 1
            wanted.append((user_id, role_name, group))
    return counts, wanted


def apply(organization, wanted, *, actor=None) -> int:
    from core.audit import log_actions
    from core.constants import AuditAction

    Membership = django_apps.get_model("organizations", "Membership")
    roles = ensure_roles(organization)
    written, entries = 0, []
    for user_id, role_name, group in wanted:
        membership, created = Membership.objects.get_or_create(
            user_id=user_id,
            organization=organization,
            role=roles[role_name],
            scope_unit=group,
            defaults={"is_active": True, "is_primary": False, "assigned_by": actor},
        )
        if not created and not membership.is_active:
            membership.is_active = True
            membership.save(update_fields=["is_active"])
        written += 1
        entries.append(
            {
                "action": AuditAction.CREATE if created else AuditAction.UPDATE,
                "user": actor,
                "organization": organization,
                "resource_type": _AUDIT_RESOURCE,
                "resource_id": str(membership.pk),
                "resource_repr": f"{role_name} @ {group.name}",
                "new_values": {"user_id": user_id, "role": role_name, "scope_unit": str(group.pk), "is_active": True},
                "reason": "Əcnəbi tələbələrlə iş şöbəsi — əcnəbi qrupu əhatəsi (sahib 2026-11-25)",
            }
        )
    if entries:
        log_actions(entries)
    return written


__all__ = ["apply", "ensure_roles", "foreign_groups", "office_members", "plan", "sync_for_group"]
