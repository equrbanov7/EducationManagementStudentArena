"""Yerləşdirmə planının TƏTBİQİ və GERİ QAYTARILMASI — auditli, paket (batch) id-li (sahib 2026-10-25).

Yazılar YALNIZ mövcud yollarla:

* ``JOIN`` → ``workload.public.join_chair_as_teacher`` (kafedrada ƏLAVƏ müəllim üzvlüyü, öz audit sətri);
* ``PRIMARY`` → ``Membership.save()`` (``is_primary`` — modelin özü təşkilatda tək əsas üzvlüyü təmin edir);
* ``DEACTIVATE`` → üzvlüyün ``is_active=False`` (silinmir; geri qaytarıla bilir).

Paketin manifesti BİR audit qeydindədir (``resource_type=accounts.staff_placement_batch``); ``undo`` onu oxuyub
yalnız hələ də bu paketin vəziyyətində qalanı qaytarır. Təkrar ``apply`` idempotentdir — plan yenidən qurulur və
artıq düzgün olan heç nə yazılmır.
"""

from __future__ import annotations

from django.utils import timezone

from apps.organizations.models import Membership
from core.audit import log_action
from core.constants import AuditAction

from ..people.constants import TEACHER_ROLE_NAMES
from ..teacher_roster.apply import RosterError, clean_reason
from .plan import DEACTIVATE, JOIN, PRIMARY

BATCH_RESOURCE = "accounts.staff_placement_batch"
UNDO_RESOURCE = "accounts.staff_placement_undo"


def new_batch_id() -> str:
    import secrets

    return f"placement-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def _audit(actor, organization, membership, *, reason, old, new):
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=membership,
        old_values=old,
        new_values=new,
        reason=reason,
    )


def _teaching_membership(organization, user_id, unit_id):
    return (
        Membership.objects.filter(
            organization=organization,
            user_id=user_id,
            scope_unit_id=unit_id,
            is_active=True,
            role__name__in=TEACHER_ROLE_NAMES,
        )
        .order_by("-is_primary", "created_at")
        .first()
    )


def _join(action, *, organization, users, units, actor, note) -> dict | None:
    from apps.workload.public import join_chair_as_teacher

    before = (
        Membership.objects.filter(
            organization=organization, user_id=action.user_id, scope_unit_id=action.unit_id, role__name="teacher"
        )
        .values("id", "is_active")
        .first()
    )
    changed = join_chair_as_teacher(
        organization=organization,
        user=users[action.user_id],
        chair=units[action.unit_id],
        actor_user=actor,
        reason=note,
    )
    if not changed:
        return None
    membership = Membership.objects.get(
        organization=organization, user_id=action.user_id, scope_unit_id=action.unit_id, role__name="teacher"
    )
    return {"membership": str(membership.pk), "user": action.user_id, "unit": action.unit_id, "existed": bool(before)}


def _primary(action, *, organization, actor, note) -> dict | None:
    target = _teaching_membership(organization, action.user_id, action.unit_id)
    if target is None or target.is_primary:
        return None
    previous = (
        Membership.objects.filter(organization=organization, user_id=action.user_id, is_primary=True)
        .values_list("pk", flat=True)
        .first()
    )
    target.is_primary = True
    target.save()  # Membership.save: təşkilatda digər əsas üzvlüklər ``is_primary=False`` olur
    _audit(actor, organization, target, reason=note, old={"is_primary": False}, new={"is_primary": True})
    return {"membership": str(target.pk), "user": action.user_id, "previous": str(previous) if previous else None}


def _deactivate(action, *, organization, actor, note) -> dict | None:
    membership = Membership.objects.filter(
        pk=action.membership_id, organization=organization, user_id=action.user_id, is_active=True
    ).first()
    if membership is None or membership.is_primary:
        return None
    membership.is_active = False
    membership.save(update_fields=["is_active", "updated_at"])
    _audit(actor, organization, membership, reason=note, old={"is_active": True}, new={"is_active": False})
    return {"membership": str(membership.pk), "user": action.user_id, "unit": action.unit_id}


def execute(plan, *, actor, reason: str, batch_id: str = "") -> dict:
    """Planı yazır (çağıran ``rls_worker_atomic`` + RLS konteksti içindədir). Sıra: JOIN → PRIMARY → DEACTIVATE."""
    from django.contrib.auth import get_user_model

    from apps.organizations.models import OrgUnit

    reason = clean_reason(reason)
    batch_id = batch_id or new_batch_id()
    organization = plan.organization
    note = f"{reason} [{batch_id}]"[:300]
    users = get_user_model().objects.in_bulk({action.user_id for action in plan.actions})
    units = {
        str(unit.pk): unit
        for unit in OrgUnit.objects.filter(
            organization=organization, pk__in={action.unit_id for action in plan.actions if action.unit_id}
        )
    }
    manifest = {"academic_year": plan.academic_year, JOIN: [], PRIMARY: [], DEACTIVATE: []}
    for kind, handler in (
        (
            JOIN,
            lambda action: _join(action, organization=organization, users=users, units=units, actor=actor, note=note),
        ),
        (PRIMARY, lambda action: _primary(action, organization=organization, actor=actor, note=note)),
        (DEACTIVATE, lambda action: _deactivate(action, organization=organization, actor=actor, note=note)),
    ):
        for action in plan.actions:
            if action.kind != kind:
                continue
            entry = handler(action)
            if entry:
                manifest[kind].append(entry)
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        changes=manifest,
        reason=reason,
        resource_type=BATCH_RESOURCE,
        resource_id=batch_id,
        resource_repr=f"Heyət yerləşdirməsi {plan.academic_year}",
    )
    return {"batch": batch_id, **manifest}


def undo(batch_id: str, *, actor, reason: str = "") -> dict:
    """Paketi geri qaytarır: deaktiv edilən üzvlük → aktiv, əsaslıq → əvvəlki, əlavə edilən üzvlük → deaktiv."""
    from apps.audit.models import AuditLog

    entry = AuditLog.objects.filter(resource_type=BATCH_RESOURCE, resource_id=batch_id).order_by("-created_at").first()
    if entry is None:
        raise RosterError("batch_not_found", f"Paket tapılmadı: {batch_id}")
    manifest = entry.changes or {}
    organization = entry.organization
    note = " ".join(str(reason or "").split()) or f"Heyət yerləşdirməsi geri qaytarıldı [{batch_id}]"
    result = {"reactivated": 0, "primary_restored": 0, "joins_reverted": 0, "skipped": 0}

    for item in manifest.get(DEACTIVATE, []):
        membership = Membership.objects.filter(pk=item["membership"], organization=organization).first()
        if membership is None or membership.is_active:
            result["skipped"] += 1
            continue
        membership.is_active = True
        membership.save(update_fields=["is_active", "updated_at"])
        _audit(actor, organization, membership, reason=note, old={"is_active": False}, new={"is_active": True})
        result["reactivated"] += 1

    for item in manifest.get(PRIMARY, []):
        previous = item.get("previous")
        current = Membership.objects.filter(pk=item["membership"], organization=organization, is_primary=True).first()
        target = (
            Membership.objects.filter(pk=previous, organization=organization, is_active=True).first()
            if previous
            else None
        )
        if current is None or target is None:
            result["skipped"] += 1
            continue
        target.is_primary = True
        target.save()
        _audit(actor, organization, target, reason=note, old={"is_primary": False}, new={"is_primary": True})
        result["primary_restored"] += 1

    for item in manifest.get(JOIN, []):
        membership = Membership.objects.filter(pk=item["membership"], organization=organization, is_active=True).first()
        if membership is None or membership.is_primary:
            result["skipped"] += 1
            continue
        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        _audit(actor, organization, membership, reason=note, old={"is_active": True}, new={"is_active": False})
        result["joins_reverted"] += 1

    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        changes=result,
        reason=note,
        resource_type=UNDO_RESOURCE,
        resource_id=batch_id,
        resource_repr=f"Heyət yerləşdirməsi {manifest.get('academic_year', '')}",
    )
    return result


__all__ = ["BATCH_RESOURCE", "UNDO_RESOURCE", "execute", "new_batch_id", "undo"]
