"""Dekanlıq laborantlarının ``lab_assistant`` → ``dean_office_assistant`` köçürülməsi (sahib 2026-11-27).

Heyət siyahısı əvvəl hər «Laborant»ı kafedra rolu ``lab_assistant``-a salırdı; fakültəyə / dekanlığa bağlı olanlar
dərs yükü və kafedra müraciətləri ilə qalır, dekanlıq işini (qruplar, tələbə hərəkəti, reyestr) görə bilmirdi.

Qayda: ``scope_unit``-i ``faculty`` / ``deanery`` tipli AKTİV ``lab_assistant`` üzvlüyü → eyni bölmədə
``dean_office_assistant``. Kafedra laborantları (``chair`` və s.) TOXUNULMUR. Eyni şəxsdə həmin bölmə üçün yeni rolun
sətri artıq varsa o aktivləşdirilir, köhnə sətir passivləşir (``unique_together`` = user + org + rol + bölmə); yoxdursa
köhnə sətrin rolu dəyişir (``is_primary`` / ``assigned_by`` qalır). Heç nə silinmir, hər sətir audit olunur.
Profil rolu (``UserProfile.role``) dəyişmir.
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps

from .default_roles_dean_office import DEAN_OFFICE_ASSISTANT_ROLE, DEAN_OFFICE_ROLES, DEAN_OFFICE_UNIT_TYPES

SOURCE_ROLE = "lab_assistant"
_AUDIT_RESOURCE = "organizations.dean_office_laborant"
_REASON = "Dekanlıq laborantı — lab_assistant → dean_office_assistant (sahib 2026-11-27)"


def ensure_role(organization):
    """Təşkilatda «Dekanlıq laborantı» rolu — yoxdursa şablondan yaradılır (miqrasiya 0089 ilə eyni dəst)."""
    Role = django_apps.get_model("organizations", "Role")
    spec = DEAN_OFFICE_ROLES[0]
    role = Role.objects.filter(organization=organization, name=DEAN_OFFICE_ASSISTANT_ROLE).first()
    if role is None:
        role = Role.objects.create(
            organization=organization,
            name=spec["name"],
            display_name=spec["display_name"],
            description=spec["description"],
            level=spec["level"],
            scope_type=spec["scope_type"],
            permissions=list(spec["permissions"]),
            is_system=True,
            is_active=True,
        )
    return role


def candidates(organization) -> list:
    """Köçürüləcək AKTİV ``lab_assistant`` üzvlükləri (fakültə / dekanlıq bölməsinə bağlı)."""
    Membership = django_apps.get_model("organizations", "Membership")
    return list(
        Membership.objects.filter(
            organization=organization,
            is_active=True,
            role__name=SOURCE_ROLE,
            scope_unit__unit_type__in=sorted(DEAN_OFFICE_UNIT_TYPES),
        )
        .select_related("user", "scope_unit", "role")
        .order_by("scope_unit__name", "user__username")
    )


def plan(organization) -> tuple[Counter, list]:
    """``(counts, rows)`` — ``rows``: ``[(membership, existing_target_or_None)]``. HEÇ NƏ YAZMIR."""
    Membership = django_apps.get_model("organizations", "Membership")
    counts: Counter = Counter()
    rows = []
    found = candidates(organization)
    existing = {
        (row.user_id, row.scope_unit_id): row
        for row in Membership.objects.filter(
            organization=organization,
            role__name=DEAN_OFFICE_ASSISTANT_ROLE,
            user_id__in=[row.user_id for row in found],
        )
    }
    for membership in found:
        target = existing.get((membership.user_id, membership.scope_unit_id))
        counts["reactivate" if target is not None else "switch"] += 1
        rows.append((membership, target))
    counts["candidates"] = len(found)
    return counts, rows


def apply(organization, rows, *, actor=None) -> int:
    """Planı tətbiq edir (çağıran tranzaksiya açır). Qaytarır: dəyişən üzvlük sayı."""
    from core.audit import log_actions
    from core.constants import AuditAction

    role = ensure_role(organization)
    entries, written = [], 0
    for membership, target in rows:
        unit = membership.scope_unit
        if target is not None:
            if not target.is_active:
                target.is_active = True
                target.save(update_fields=["is_active"])
            membership.is_active = False
            membership.save(update_fields=["is_active"])
            resource_id, old_values = str(target.pk), {"role": SOURCE_ROLE, "membership_id": str(membership.pk)}
        else:
            membership.role = role
            membership.save(update_fields=["role"])
            resource_id, old_values = str(membership.pk), {"role": SOURCE_ROLE}
        written += 1
        entries.append(
            {
                "action": AuditAction.UPDATE,
                "user": actor,
                "organization": organization,
                "resource_type": _AUDIT_RESOURCE,
                "resource_id": resource_id,
                "resource_repr": f"{DEAN_OFFICE_ASSISTANT_ROLE} @ {unit.name}",
                "old_values": old_values,
                "new_values": {
                    "user_id": membership.user_id,
                    "role": DEAN_OFFICE_ASSISTANT_ROLE,
                    "scope_unit": str(unit.pk),
                    "is_active": True,
                },
                "reason": _REASON,
            }
        )
    if entries:
        log_actions(entries)
    return written


__all__ = ["SOURCE_ROLE", "apply", "candidates", "ensure_role", "plan"]
