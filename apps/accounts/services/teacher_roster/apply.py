"""Planın TƏTBİQİ və GERİ QAYTARILMASI — auditli, paket (batch) id-li (sahib 2026-10-11).

* elmi ad/dərəcə → ``UserProfile`` (fərq varsa), yük profili → ``apps.workload.public.sync_roster_profile``;
* bloklama MÖVCUD servislə (``account_deletion.block_account`` — «Hesabı dayandır» dialoqunun özəyi):
  səbəb kodu ``employment_ended``, müraciət ``hr``; ``block_reason`` mətninə ``[<batch>]`` markeri yazılır.
  Hesab adi «Blokdan çıxar» ilə də açıla bilir;
* paketin manifesti (kim bloklandı, hansı sahə köhnə → yeni) BİR audit qeydində saxlanılır
  (``resource_type=accounts.teacher_roster_batch``, ``resource_id=<batch>``) — ``undo`` onu oxuyur.

``undo`` yalnız HƏLƏ də bu paketin vəziyyətində qalanı qaytarır: başqa səbəblə yenidən bloklanmış və ya
sonradan əl ilə dəyişdirilmiş sahələrə toxunmur. Təkrar ``undo`` zərərsizdir (idempotent).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .. import account_block_reasons as block_reasons
from ..account_deletion import AccountDeletionError, block_account, unblock_account

BATCH_RESOURCE = "accounts.teacher_roster_batch"
UNDO_RESOURCE = "accounts.teacher_roster_undo"
BLOCK_REASON_CODE = "employment_ended"
BLOCK_CONTACT_CODE = "hr"
BLOCK_CONTACT_NOTE = "Müqaviləniz davam edirsə, kafedra müdirinizə və ya kadrlar şöbəsinə yaxınlaşın."
MIN_REASON_LENGTH = 20


class RosterError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(code, message)
        self.code, self.message = code, message


def new_batch_id() -> str:
    import secrets

    return f"roster-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def marker(batch_id: str) -> str:
    return f"[{batch_id}]"


def clean_reason(reason: str) -> str:
    text = " ".join(str(reason or "").split())
    if len(text) < MIN_REASON_LENGTH:
        raise RosterError("reason_required", f"--reason ən azı {MIN_REASON_LENGTH} simvol olmalıdır.")
    return text[:300]


def block_text(batch_id: str, academic_year: str) -> str:
    label = block_reasons.audit_text(BLOCK_REASON_CODE, "")
    return f"{label} — «Forma 7» ({academic_year}) siyahısında yoxdur {marker(batch_id)}"[:300]


def _apply_profile(user, changes: dict, *, actor, organization, batch_id) -> dict | None:
    profile = getattr(user, "profile", None)
    if profile is None or not changes:
        return None
    before = {field: getattr(profile, field) for field in changes}
    for field, (_old, new) in changes.items():
        setattr(profile, field, new)
    profile.save(update_fields=[*changes.keys(), "updated_at"])
    after = {field: new for field, (_old, new) in changes.items()}
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=profile,
        old_values=before,
        new_values=after,
        reason=f"Forma 7 tutuşdurması {marker(batch_id)}",
        resource_type="accounts.UserProfile",
        resource_id=str(user.pk),
        resource_repr=user.get_full_name() or user.username,
    )
    return {"user": user.pk, "before": before, "after": after}


def execute(plan, *, actor, reason: str, batch_id: str = "", do_updates=True, do_blocks=True) -> dict:
    """Planı yazır. Çağıran ``rls_worker_atomic`` + RLS konteksti içində olmalıdır (bir tranzaksiya)."""
    from apps.workload.public import sync_roster_profile

    reason = clean_reason(reason)
    batch_id = batch_id or new_batch_id()
    organization = plan.organization
    users = (
        get_user_model()
        .objects.select_related("profile")
        .in_bulk([*plan.users.keys(), *(account.user_id for account in plan.block)])
    )
    manifest = {"academic_year": plan.academic_year, "profiles": [], "workload": [], "blocked": [], "failed": []}

    if do_updates:
        for user_id, user_plan in plan.users.items():
            user = users[user_id]
            entry = _apply_profile(
                user, user_plan.profile_changes, actor=actor, organization=organization, batch_id=batch_id
            )
            if entry:
                manifest["profiles"].append(entry)
            if user_plan.position is None and user_plan.staff_fraction is None:
                continue
            result = sync_roster_profile(
                organization=organization,
                teacher=user,
                academic_year=plan.academic_year,
                position=user_plan.position,
                staff_fraction=user_plan.staff_fraction,
                is_external=user_plan.is_external,
                actor=actor,
                reason=f"Forma 7 tutuşdurması {marker(batch_id)}",
                dry_run=False,
            )
            if result["changed"]:
                manifest["workload"].append({"user": user_id, "before": result["before"], "after": result["after"]})

    if do_blocks:
        text = block_text(batch_id, plan.academic_year)
        for account in plan.block:
            user = users[account.user_id]
            if not user.is_active:
                continue
            try:
                block_account(
                    user,
                    actor=actor,
                    reason=text,
                    reason_code=BLOCK_REASON_CODE,
                    contact_code=BLOCK_CONTACT_CODE,
                    contact_note=BLOCK_CONTACT_NOTE,
                )
            except AccountDeletionError as exc:
                manifest["failed"].append({"user": account.user_id, "error": str(exc)})
                continue
            manifest["blocked"].append(account.user_id)

    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        changes=manifest,
        reason=reason,
        resource_type=BATCH_RESOURCE,
        resource_id=batch_id,
        resource_repr=f"Forma 7 {plan.academic_year}",
    )
    return {"batch": batch_id, **manifest}


def _manifest(batch_id: str):
    from apps.audit.models import AuditLog

    entry = AuditLog.objects.filter(resource_type=BATCH_RESOURCE, resource_id=batch_id).order_by("-created_at").first()
    if entry is None:
        raise RosterError("batch_not_found", f"Paket tapılmadı: {batch_id}")
    return entry


def undo(batch_id: str, *, actor, reason: str = "") -> dict:
    """Paketi geri qaytarır (bloklar → açılır, sahələr → köhnə dəyər)."""
    from apps.workload.public import restore_roster_profile

    entry = _manifest(batch_id)
    manifest = entry.changes or {}
    organization = entry.organization
    year = manifest.get("academic_year", "")
    tag = marker(batch_id)
    note = " ".join(str(reason or "").split()) or f"Forma 7 paketi geri qaytarıldı {tag}"
    ids = {*manifest.get("blocked", []), *(item["user"] for item in manifest.get("profiles", []))}
    ids |= {item["user"] for item in manifest.get("workload", [])}
    users = get_user_model().objects.select_related("profile").in_bulk(list(ids))
    result = {"batch": batch_id, "unblocked": [], "profiles": 0, "workload": {}, "skipped": []}

    for user_id in manifest.get("blocked", []):
        user = users.get(user_id)
        profile = getattr(user, "profile", None) if user else None
        if user is None or user.is_active or profile is None or tag not in (profile.block_reason or ""):
            result["skipped"].append(user_id)
            continue
        try:
            unblock_account(user, actor=actor, reason=note)
        except AccountDeletionError:
            result["skipped"].append(user_id)
            continue
        result["unblocked"].append(user_id)

    for item in manifest.get("profiles", []):
        profile = getattr(users.get(item["user"]), "profile", None)
        if profile is None:
            continue
        restore = {
            field: old
            for field, old in item["before"].items()
            if getattr(profile, field) == item["after"].get(field) != old
        }
        if restore:
            for field, old in restore.items():
                setattr(profile, field, old)
            profile.save(update_fields=[*restore.keys(), "updated_at"])
            result["profiles"] += 1

    for item in manifest.get("workload", []):
        user = users.get(item["user"])
        if user is None:
            continue
        outcome = restore_roster_profile(
            organization=organization,
            teacher=user,
            academic_year=year,
            before=item["before"],
            after=item["after"],
            actor=actor,
            reason=note,
        )
        result["workload"][outcome] = result["workload"].get(outcome, 0) + 1

    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        changes={key: value for key, value in result.items() if key != "batch"},
        reason=note,
        resource_type=UNDO_RESOURCE,
        resource_id=batch_id,
        resource_repr=f"Forma 7 {year}",
    )
    return result


__all__ = [
    "BATCH_RESOURCE",
    "BLOCK_CONTACT_CODE",
    "BLOCK_REASON_CODE",
    "RosterError",
    "block_text",
    "clean_reason",
    "execute",
    "marker",
    "new_batch_id",
    "undo",
]
