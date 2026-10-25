"""Dublikat planının TƏTBİQİ və GERİ QAYTARILMASI — auditli, paket (batch) id-li (sahib 2026-10-25).

Yazılar YALNIZ mövcud yollarla, hər dublikat öz savepoint-ində (biri alınmasa digərləri yazılır):

1. **rollar** — dublikatın aktiv üzvlüyü (rol + bölmə) saxlanılanda yoxdursa saxlanılana verilir (yaradılır və ya
   deaktiv üzvlük aktivləşdirilir; ``is_primary=False`` — saxlanılanın əsas kafedrası dəyişmir);
2. **rəhbərlik** — dublikatın rəhbəri olduğu bölmənin ``OrgUnit.head``-i saxlanılan olur;
3. **jurnallar** — cari açılışlar rəsmi «Fənn təhvili» ilə (``registrar.handover_actions.bulk_reassign``:
   blokerlər, ``TeachingHandover`` sətri, audit, yeni müəllimə bildiriş) saxlanılana keçir;
4. **üzvlüklər** — dublikatın aktiv üzvlükləri ``is_active=False`` (silinmir);
5. **dondurma** — «Hesabı dayandır» (``account_deletion.block_account``): səbəb «Digər — Dublikat hesab — əsas
   hesab: <istifadəçi adı>», müraciət RİM; giriş cəhdində şəxs əsas hesabın adını görür.

Paketin manifesti BİR audit qeydindədir (``resource_type=accounts.duplicate_accounts_batch``). ``undo`` yalnız
hələ də bu paketin vəziyyətində qalanı qaytarır (təhvillər ``handover_actions.revert`` ilə).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.organizations.models import Membership, OrgUnit
from core.audit import log_action
from core.constants import AuditAction

from .. import account_block_reasons as block_reasons
from ..account_deletion import AccountDeletionError, block_account, unblock_account
from ..teacher_roster.apply import RosterError
from .plan import STATUS_OK

BATCH_RESOURCE = "accounts.duplicate_accounts_batch"
UNDO_RESOURCE = "accounts.duplicate_accounts_undo"
BLOCK_REASON_CODE = "other"
BLOCK_CONTACT_CODE = "rim"
DEFAULT_REASON = "Sahibin 2026-10-25 qərarı: dublikat hesab — jurnal yazılan hesab saxlanılır, digərləri dondurulur"
HANDOVER_CHUNK = 100


def new_batch_id() -> str:
    import secrets

    return f"dupacct-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def block_text(kept_username: str) -> str:
    """``UserProfile.block_reason`` — «Digər» formatı (``display_reason`` izahı şəxsə göstərir)."""
    return block_reasons.audit_text(BLOCK_REASON_CODE, "", f"Dublikat hesab — əsas hesab: {kept_username}")[:300]


def contact_note(kept_username: str) -> str:
    return f"Əsas hesabınızla daxil olun: {kept_username}. Parolu bilmirsinizsə RİM-ə müraciət edin."[:200]


def _audit(actor, organization, obj, *, reason, old, new):
    log_action(AuditAction.UPDATE, user=actor, organization=organization, obj=obj, old_values=old, new_values=new,
               reason=reason)  # fmt: skip


def _give_role(organization, kept, membership: dict, *, actor, note) -> dict | None:
    existing = Membership.objects.filter(
        organization=organization, user=kept, role_id=membership["role_id"], scope_unit_id=membership["unit"]
    ).first()
    if existing is not None and existing.is_active:
        return None
    if existing is None:
        existing = Membership.objects.create(
            organization=organization,
            user=kept,
            role_id=membership["role_id"],
            scope_unit_id=membership["unit"],
            title=membership["title"],
            assigned_by=actor,
            is_primary=False,
            is_active=True,
        )
        log_action(AuditAction.CREATE, user=actor, organization=organization, obj=existing, reason=note,
                   new_values={"user": kept.username, "role": membership["role"], "unit": membership["unit"]})  # fmt: skip
        return {"membership": str(existing.pk), "created": True}
    existing.is_active = True
    existing.assigned_by = actor
    existing.save(update_fields=["is_active", "assigned_by", "updated_at"])
    _audit(actor, organization, existing, reason=note, old={"is_active": False}, new={"is_active": True})
    return {"membership": str(existing.pk), "created": False}


def _move_heads(organization, unit_ids, dup, kept, *, actor, note) -> list:
    moved = []
    for unit in OrgUnit.objects.filter(organization=organization, pk__in=unit_ids, head=dup):
        unit.head = kept
        unit.save(update_fields=["head", "updated_at"])
        _audit(actor, organization, unit, reason=note, old={"head": dup.username}, new={"head": kept.username})
        moved.append(str(unit.pk))
    return moved


def _handover(organization, offering_ids, dup, kept, *, actor, note) -> list:
    from django.apps import apps as django_apps

    from apps.registrar.public import handover_actions

    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    live = [
        str(pk)
        for pk in CourseOffering.objects.filter(
            organization=organization, pk__in=offering_ids, instructor=dup
        ).values_list("pk", flat=True)
    ]
    handovers = []
    for start in range(0, len(live), HANDOVER_CHUNK):
        items = [{"offering_id": pk, "new_instructor_id": kept.pk} for pk in live[start : start + HANDOVER_CHUNK]]
        result = handover_actions.bulk_reassign(actor=actor, organization=organization, items=items, reason=note)
        handovers.extend(result["handover_ids"])
    return handovers


def _deactivate(organization, membership_ids, dup, *, actor, note) -> list:
    done = []
    for membership in Membership.objects.filter(organization=organization, user=dup, pk__in=membership_ids,
                                                is_active=True):  # fmt: skip
        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        _audit(actor, organization, membership, reason=note, old={"is_active": True}, new={"is_active": False})
        done.append(str(membership.pk))
    return done


def _apply_dup(organization, action, kept, users, *, actor, note) -> dict:
    dup = users[action.person.user_id]
    entry = {"kept": kept.pk, "dup": dup.pk, "roles": [], "heads": [], "handovers": [], "deactivated": [],
             "blocked": False, "block_text": ""}  # fmt: skip
    for membership in action.transfer:
        given = _give_role(organization, kept, membership, actor=actor, note=note)
        if given:
            entry["roles"].append(given)
    entry["heads"] = _move_heads(organization, action.heads, dup, kept, actor=actor, note=note)
    entry["handovers"] = _handover(organization, action.handover, dup, kept, actor=actor, note=note)
    entry["deactivated"] = _deactivate(organization, action.deactivate, dup, actor=actor, note=note)
    if action.block and dup.is_active:
        text = block_text(kept.username)
        block_account(dup, actor=actor, reason=text, reason_code=BLOCK_REASON_CODE,
                      contact_code=BLOCK_CONTACT_CODE, contact_note=contact_note(kept.username))  # fmt: skip
        entry["blocked"], entry["block_text"] = True, text
    return entry


def execute(plan, *, actor, reason: str = "", batch_id: str = "") -> dict:
    """Planı yazır (çağıran ``rls_worker_atomic`` + RLS konteksti içindədir)."""
    from apps.registrar.public import handover_actions

    reason = " ".join(str(reason or "").split()) or DEFAULT_REASON
    if len(reason) < 20:
        raise RosterError("reason_required", "--reason ən azı 20 simvol olmalıdır.")
    batch_id = batch_id or new_batch_id()
    organization = plan.organization
    note = f"{reason} [{batch_id}]"[:300]
    clusters = [cluster for cluster in plan.clusters if cluster.status == STATUS_OK and cluster.writes]
    ids = {cluster.kept.user_id for cluster in clusters}
    ids |= {action.person.user_id for cluster in clusters for action in cluster.dups}
    users = get_user_model().objects.select_related("profile").in_bulk(list(ids))
    manifest = {"academic_year": plan.academic_year, "pairs": [], "failed": []}
    for cluster in clusters:
        kept = users[cluster.kept.user_id]
        for action in cluster.dups:
            if action.skip or not action.writes:
                continue
            try:
                with transaction.atomic():
                    entry = _apply_dup(organization, action, kept, users, actor=actor, note=note)
            except (handover_actions.HandoverError, PermissionDenied, AccountDeletionError, DatabaseError) as exc:
                manifest["failed"].append({"kept": kept.pk, "dup": action.person.user_id, "error": str(exc)[:200]})
                continue
            entry["mode"] = cluster.mode
            manifest["pairs"].append(entry)
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        changes=manifest,
        reason=reason,
        resource_type=BATCH_RESOURCE,
        resource_id=batch_id,
        resource_repr=f"Dublikat hesablar {plan.academic_year}",
    )
    return {"batch": batch_id, **manifest}


def _undo_pair(organization, entry, users, *, actor, note, result) -> None:
    """Sıra vacibdir: DB triggeri jurnal sahibinin AKTİV üzv olmasını tələb edir — əvvəl blok açılır və
    üzvlüklər qayıdır, sonra təhvillər geri alınır, sonda saxlanılana verilən rollar geri götürülür."""
    from apps.registrar.public import handover_actions

    dup, kept = users.get(entry["dup"]), users.get(entry["kept"])
    if dup is None or kept is None:
        result["skipped"] += 1
        return
    if entry.get("blocked"):
        profile = getattr(dup, "profile", None)
        if not dup.is_active and profile is not None and profile.block_reason == entry.get("block_text"):
            unblock_account(dup, actor=actor, reason=note)
            result["unblocked"] += 1
        else:
            result["skipped"] += 1
    for membership in Membership.objects.filter(pk__in=entry.get("deactivated", []), user=dup, is_active=False):
        membership.is_active = True
        membership.save(update_fields=["is_active", "updated_at"])
        _audit(actor, organization, membership, reason=note, old={"is_active": False}, new={"is_active": True})
        result["memberships_restored"] += 1
    for handover_id in reversed(entry.get("handovers", [])):
        try:
            with transaction.atomic():
                handover_actions.revert(actor=actor, organization=organization, handover_id=handover_id, reason=note)
            result["handovers_reverted"] += 1
        except (handover_actions.HandoverError, PermissionDenied, DatabaseError):
            result["skipped"] += 1
    for unit in OrgUnit.objects.filter(organization=organization, pk__in=entry.get("heads", []), head=kept):
        unit.head = dup
        unit.save(update_fields=["head", "updated_at"])
        _audit(actor, organization, unit, reason=note, old={"head": kept.username}, new={"head": dup.username})
        result["heads_restored"] += 1
    role_ids = [item["membership"] for item in entry.get("roles", [])]
    for membership in Membership.objects.filter(pk__in=role_ids, user=kept, is_active=True):
        membership.is_active = False
        membership.save(update_fields=["is_active", "updated_at"])
        _audit(actor, organization, membership, reason=note, old={"is_active": True}, new={"is_active": False})
        result["roles_withdrawn"] += 1


def undo(batch_id: str, *, actor, reason: str = "") -> dict:
    """Paketi geri qaytarır: təhvillər → geri, blok → açılır, üzvlüklər/rəhbərlik → əvvəlki, verilən rollar → deaktiv."""
    from apps.audit.models import AuditLog

    entry = AuditLog.objects.filter(resource_type=BATCH_RESOURCE, resource_id=batch_id).order_by("-created_at").first()
    if entry is None:
        raise RosterError("batch_not_found", f"Paket tapılmadı: {batch_id}")
    manifest = entry.changes or {}
    organization = entry.organization
    note = " ".join(str(reason or "").split()) or f"Dublikat hesab paketi geri qaytarıldı [{batch_id}]"
    pairs = manifest.get("pairs", [])
    ids = {item["dup"] for item in pairs} | {item["kept"] for item in pairs}
    users = get_user_model().objects.select_related("profile").in_bulk(list(ids))
    result = {"handovers_reverted": 0, "unblocked": 0, "memberships_restored": 0, "heads_restored": 0,
              "roles_withdrawn": 0, "skipped": 0, "failed": 0}  # fmt: skip
    for item in reversed(pairs):
        try:
            with transaction.atomic():
                _undo_pair(organization, item, users, actor=actor, note=note, result=result)
        except (AccountDeletionError, DatabaseError):
            result["failed"] += 1
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        changes=result,
        reason=note,
        resource_type=UNDO_RESOURCE,
        resource_id=batch_id,
        resource_repr=f"Dublikat hesablar {manifest.get('academic_year', '')}",
    )
    return result


__all__ = ["BATCH_RESOURCE", "DEFAULT_REASON", "UNDO_RESOURCE", "block_text", "execute", "new_batch_id", "undo"]
