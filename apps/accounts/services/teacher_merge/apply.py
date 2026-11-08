"""Müəllim dublikatının əsas hesaba BİRLƏŞDİRİLMƏSİ (sahib 2026-11-08: Fatma — 7794 → 8170).

Bir tranzaksiyada (çağıranınkı), qapılar (:mod:`.guards`) keçdikdən sonra bu sırada:

1. **rollar** — hədəfin aktiv ``grade.input`` üzvlüyü olmalıdır (jurnal sahibi / dərs müəllimi trigger-i bunu
   tələb edir): mənbənin AKTİV heyət üzvlükləri (rol + bölmə) hədəfdə yoxdursa verilir (yaradılır və ya deaktiv
   üzvlük aktivləşir; ``is_primary`` dəyişmir). Hədəfin hələ də ``grade.input``-u yoxdursa mənbənin (deaktiv)
   ``grade.input`` üzvlüyü, o da yoxdursa təşkilatın ``teacher`` rolu verilir;
2. **paylar** — :mod:`.shares` (açılışın müəllimi hələ dəyişməmiş halda);
3. **sətirlər** — :data:`policy.POLICY`-də ``repoint`` olan HƏR sahə: toqquşmayan sətirlər hədəfə keçir
   (``moved_<sahə>``), unikal toqquşma mənbədə qalır (``collision_<sahə>``), DB-nin rədd etdiyi sətir qalır
   (``blocked_<sahə>``); 2 saat jurnal qoruyucusu ``journal_unlock`` ilə açılır (müəlliflik sahəsi dəyişir, bal yox);
4. **qalanlar** — ``keep_*`` sahələrində mənbədə qalan sətirlər sayılır (``kept_<sahə>``);
5. **mənbə** — aktiv üzvlükləri ``is_active=False``; hesab aktivdirsə «Hesabı dayandır» (səbəb «Digər — Dublikat
   müəllim hesabı — əsas hesab: …»); artıq bloklanıbsa toxunulmur. Hesab SİLİNMİR.

Manifest (köçən id-lər, verilən rollar, pay dəyişiklikləri) BİR audit sətrindədir
(``accounts.teacher_merge_batch``, ``resource_id`` = paket); :mod:`.undo` onu geri qaytarır.
"""

from __future__ import annotations

import secrets
from collections import Counter

from django.apps import apps as django_apps
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction
from core.rls import journal_unlock

from .. import account_block_reasons as block_reasons
from ..account_deletion import block_account
from . import guards, policy, repoint, shares

BATCH_RESOURCE = "accounts.teacher_merge_batch"
BLOCK_REASON_CODE = "other"
BLOCK_CONTACT_CODE = "rim"
TEACHER_ROLE = "teacher"
SHOWN = (
    "merged",
    "relations_checked",
    "rows_moved",
    "rows_collision_kept",
    "rows_blocked_kept",
    "rows_kept",
    "memberships_created",
    "memberships_activated",
    "memberships_deactivated",
    "shares_moved",
    "shares_history_moved",
    "shares_collapsed",
    "shares_redundant_deactivated",
    "shares_owner_full_deactivated",
    "source_blocked",
    "source_already_blocked",
)


def new_batch() -> str:
    return f"tmerge-{timezone.localtime():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def block_text(target_username: str) -> str:
    text = f"Dublikat müəllim hesabı — əsas hesab: {target_username}"
    return block_reasons.audit_text(BLOCK_REASON_CODE, "", text)[:300]


def new_manifest(source, target) -> dict:
    return {"source": source.pk, "target": target.pk, "moved": {}, "memberships_created": [],
            "memberships_activated": [], "memberships_deactivated": [],
            "shares": {"deactivated": [], "updated": []}, "blocked": False, "block_text": ""}  # fmt: skip


def _give(organization, target, membership, *, actor, manifest, counts) -> None:
    membership_model = django_apps.get_model("organizations", "Membership")
    existing = membership_model.objects.filter(
        organization=organization, user=target, role_id=membership.role_id, scope_unit_id=membership.scope_unit_id
    ).first()
    if existing is not None and existing.is_active:
        return
    if existing is None:
        created = membership_model.objects.create(
            organization=organization, user=target, role_id=membership.role_id, scope_unit_id=membership.scope_unit_id,
            title=membership.title, assigned_by=actor, is_primary=False, is_active=True,
        )  # fmt: skip
        manifest["memberships_created"].append(str(created.pk))
        counts["memberships_created"] += 1
        return
    membership_model.objects.filter(pk=existing.pk).update(is_active=True, updated_at=timezone.now())
    manifest["memberships_activated"].append(str(existing.pk))
    counts["memberships_activated"] += 1


def _ensure_roles(organization, source, target, *, actor, manifest, counts) -> None:
    membership_model = django_apps.get_model("organizations", "Membership")
    rows = list(
        membership_model.objects.filter(organization=organization, user=source)
        .exclude(role__name=guards.STUDENT_ROLE)
        .select_related("role")
        .order_by("-is_active", "created_at", "pk")
    )
    for membership in rows:
        if membership.is_active:
            _give(organization, target, membership, actor=actor, manifest=manifest, counts=counts)
    if guards.has_grade_input(organization, target):
        return
    for membership in rows:
        if guards.grants_grade_input(membership.role) and membership.role.is_active:
            _give(organization, target, membership, actor=actor, manifest=manifest, counts=counts)
            return
    role = (
        django_apps.get_model("organizations", "Role")
        .objects.filter(organization=organization, name=TEACHER_ROLE, is_active=True)
        .first()
    )
    if role is None or not guards.grants_grade_input(role):
        raise guards.MergeError("target_no_teacher_role")
    stub = membership_model(role_id=role.pk, scope_unit_id=None, title="")
    _give(organization, target, stub, actor=actor, manifest=manifest, counts=counts)


def _repoint_all(source, target, manifest, counts) -> None:
    with journal_unlock():
        for relation in policy.relations():
            if policy.POLICY.get(relation.key) != policy.REPOINT:
                continue
            counts["relations_checked"] += 1
            ids = repoint.source_ids(relation, source.pk)
            if not ids:
                continue
            clash = repoint.colliding_ids(relation, source.pk, target.pk)
            moved, failed = repoint.move(relation, [pk for pk in ids if pk not in clash], source.pk, target.pk)
            if moved:
                manifest["moved"].setdefault(relation.key, []).extend(str(pk) for pk in moved)
                counts[f"moved_{relation.short}"] += len(moved)
                counts["rows_moved"] += len(moved)
            if clash:
                counts[f"collision_{relation.short}"] += len(clash)
                counts["rows_collision_kept"] += len(clash)
            if failed:
                counts[f"blocked_{relation.short}"] += len(failed)
                counts["rows_blocked_kept"] += len(failed)


def _count_kept(source, counts) -> None:
    for relation in policy.relations():
        if policy.POLICY.get(relation.key) not in policy.KEEP or relation.key == "accounts.UserProfile.user":
            continue
        kept = relation.model._base_manager.filter(**{relation.attname: source.pk}).count()
        if kept:
            counts[f"kept_{relation.short}"] += kept
            counts["rows_kept"] += kept


def _retire_source(organization, source, target, *, actor, manifest, counts) -> None:
    membership_model = django_apps.get_model("organizations", "Membership")
    active = membership_model.objects.filter(organization=organization, user=source, is_active=True)
    for pk in active.values_list("pk", flat=True):
        manifest["memberships_deactivated"].append(str(pk))
    counts["memberships_deactivated"] += active.update(is_active=False, updated_at=timezone.now())
    if not source.is_active:
        counts["source_already_blocked"] += 1
        return
    text = block_text(target.username)
    block_account(
        source,
        actor=actor,
        reason=text,
        reason_code=BLOCK_REASON_CODE,
        contact_code=BLOCK_CONTACT_CODE,
        contact_note=f"Əsas hesabınızla daxil olun: {target.username}."[:200],
    )
    manifest["blocked"], manifest["block_text"] = True, text
    counts["source_blocked"] += 1


def execute(organization, source_id: int, target_id: int, *, actor, batch: str) -> Counter:
    """Cütü birləşdir (çağıranın tranzaksiyasında). Saylar qaytarılır; dəyişiklik varsa audit sətri yazılır."""
    source, target = guards.load_pair(source_id, target_id)
    guards.check(organization, source, target)
    counts: Counter = Counter()
    manifest = new_manifest(source, target)
    _ensure_roles(organization, source, target, actor=actor, manifest=manifest, counts=counts)
    shares.collapse(organization, source, target, manifest, counts)
    _repoint_all(source, target, manifest, counts)
    _retire_source(organization, source, target, actor=actor, manifest=manifest, counts=counts)
    _count_kept(source, counts)
    changed = (
        any(manifest["moved"].values())
        or any(manifest[key] for key in ("memberships_created", "memberships_activated", "memberships_deactivated"))
        or any(manifest["shares"].values())
        or manifest["blocked"]
    )
    counts["merged"] = 1 if changed else 0
    if changed:
        manifest["moved"] = {key: ids for key, ids in manifest["moved"].items() if ids}
        log_action(
            AuditAction.UPDATE,
            user=actor,
            organization=organization,
            new_values={"counts": dict(counts), "manifest": manifest},
            reason=f"merge_duplicate_teacher {batch}",
            resource_type=BATCH_RESOURCE,
            resource_id=batch,
            resource_repr=batch,
        )
    return counts


__all__ = ["BATCH_RESOURCE", "SHOWN", "block_text", "execute", "new_batch"]
