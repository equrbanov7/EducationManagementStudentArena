"""Kafedranın başqa kafedraya QOVUŞMASI — vahid tərəfi (sahib 2026-10-25).

Sahib: «Xarici dillər kafedrası olub, ora rəsmi olaraq elə dəyişib — ona birləşdir.» Struktur planının
``merge`` qaydası (:mod:`.structure_plan`) ilə EYNİ izdir: köhnə vahid ``settings["history"]``-yə
``merged_into`` / ``merged_into_name`` qeydi alır və arxivlənir (``is_active=False``, heç nə silinmir);
hədəf vahid köhnə adı ``settings["aliases"]``-ə alır — siyahı/heyət idxalı (``staff_roster.match_unit``)
köhnə başlığı DƏQİQ hədəfə bağlayır, kafedra reyestrinin axtarışı köhnə adla hədəfi tapır.

Burada YALNIZ ``organizations`` tərəfi: üzvlüklər, rəhbər, alt vahidlər, tarixçə, arxiv. Dərs yükü,
fənn kataloqu və sillabuslar ``workload.services.chair_merge``-dədir (əmr: ``merge_chair_units``).

ÜZVLÜK QAYDASI — yalnız AKTİV üzvlüklər köçür (qeyri-aktivlər tarixçədir, köhnə vahiddə qalır):

* hədəfdə eyni (istifadəçi, rol) üzvlüyü YOXDURSA — ``scope_unit`` hədəfə dəyişir (``is_primary`` qalır);
* AKTİV dublikat varsa — mənbə söndürülür, mənbə əsas idisə hədəf əsas olur;
* QEYRİ-AKTİV dublikat varsa — o yenidən aktivləşir (mənbənin ``is_primary``-si ilə), mənbə söndürülür;
* kafedra müdiri (``chair_head``) — hədəfin rəhbəri yoxdursa köçür və ``head`` olur; varsa söndürülür
  (iki müdir yaranmır; ``head_conflict`` sayılır — müəllim üzvlüyü ayrıca köçür).

İDEMPOTENT: ikinci qaçış heç nə dəyişmir (``already_merged=1``, digər saylar 0).
"""

from __future__ import annotations

from collections import Counter

from core.audit import log_action, log_actions
from core.constants import AuditAction

from .kafedra_units import kafedra_unit_types
from .models import Membership, OrgUnit
from .structure_plan import norm

#: Tarixçə qeydinin ``source``-u (struktur planındakı ``plan["source"]`` analoqu).
MERGE_SOURCE = "chair-merge"
CHAIR_HEAD_ROLE = "chair_head"


def _merged_into(unit, target) -> bool:
    return any(entry.get("merged_into") == str(target.pk) for entry in ((unit.settings or {}).get("history") or []))


def resolve_merge_units(organization, source_name: str, target_name: str):
    """``(mənbə, hədəf, artıq_qovuşub)`` — adla (AZ hərf qatlaması, registrsiz); tapılmasa ``None``.

    Hədəf AKTİV kafedra olmalıdır. Mənbə: aktiv kafedra; yoxdursa artıq bu hədəfə qovuşmuş arxiv
    vahid (təkrar qaçış). Eyni adda bir neçə aktiv vahid → ``ValueError`` (təxmin edilmir).
    """
    types = kafedra_unit_types(organization)
    units = list(OrgUnit.objects.filter(organization=organization, unit_type__in=types))

    def _pick(name, *, active):
        hits = [unit for unit in units if unit.is_active == active and norm(unit.name) == norm(name)]
        if len(hits) > 1:
            raise ValueError("ambiguous_unit")
        return hits[0] if hits else None

    target = _pick(target_name, active=True)
    if target is None:
        return None, None, False
    source = _pick(source_name, active=True)
    if source is not None:
        return (None, target, False) if source.pk == target.pk else (source, target, False)
    archived = [
        unit
        for unit in units
        if not unit.is_active and norm(unit.name) == norm(source_name) and _merged_into(unit, target)
    ]
    return (archived[0], target, True) if len(archived) == 1 else (None, target, False)


def _has_head(target) -> bool:
    if target.head_id:
        return True
    return Membership.objects.filter(
        scope_unit=target, is_active=True, role__name=CHAIR_HEAD_ROLE, role__is_active=True
    ).exists()


def _move_memberships(organization, source, target, counts: Counter) -> list:
    """Aktiv üzvlükləri köçürür → audit qeydləri (``log_actions`` üçün)."""
    entries = []
    counts["memberships_inactive_kept"] = Membership.objects.filter(scope_unit=source, is_active=False).count()
    for membership in (
        Membership.objects.filter(scope_unit=source, is_active=True).select_related("role").order_by("created_at")
    ):
        role_name = membership.role.name
        old = {"scope_unit": str(source.pk), "is_active": True, "is_primary": membership.is_primary}
        if role_name == CHAIR_HEAD_ROLE and _has_head(target) and target.head_id != membership.user_id:
            membership.is_active = False
            membership.save(update_fields=["is_active", "updated_at"])
            counts["head_conflict"] += 1
            entries.append((membership, old, {"is_active": False}))
            continue
        twin = Membership.objects.filter(
            organization=organization, user_id=membership.user_id, role_id=membership.role_id, scope_unit=target
        ).first()
        if twin is None:
            membership.scope_unit = target
            membership.save(update_fields=["scope_unit", "updated_at"])
            counts["memberships_moved"] += 1
            if role_name == CHAIR_HEAD_ROLE and not target.head_id:
                target.head_id = membership.user_id
                target.save(update_fields=["head", "updated_at"])
                counts["head_moved"] += 1
            entries.append((membership, old, {"scope_unit": str(target.pk)}))
            continue
        # Mənbə ƏVVƏL söndürülür və əsaslığı götürülür: ``Membership.save`` əsas üzvlüyü yazanda istifadəçinin
        # digər əsas üzvlüklərini sıfırlayır — sıra tərs olsa hədəfin yeni əsaslığı itərdi.
        was_primary = membership.is_primary
        membership.is_active = False
        membership.is_primary = False
        membership.save(update_fields=["is_active", "is_primary", "updated_at"])
        if twin.is_active:
            counts["memberships_deduplicated"] += 1
            if was_primary and not twin.is_primary:
                twin.is_primary = True
                twin.save(update_fields=["is_primary", "updated_at"])
        else:
            twin.is_active = True
            twin.is_primary = was_primary
            twin.save(update_fields=["is_active", "is_primary", "updated_at"])
            counts["memberships_reactivated"] += 1
        entries.append((membership, old, {"is_active": False, "is_primary": False, "kept_membership": str(twin.pk)}))
    return entries


def _history_entry(unit, date, names) -> dict:
    return {
        "date": date,
        "source": MERGE_SOURCE,
        "name": unit.name,
        "parent": names.get(unit.parent_id, ""),
        "parent_id": str(unit.parent_id) if unit.parent_id else "",
    }


def merge_chair_unit(organization, source, target, *, actor=None, date: str = "", reason: str = "") -> Counter:
    """Mənbə kafedranı hədəfə qovuşdurur (YAZIR — dry-run çağıranın tranzaksiya geri qaytarmasıdır)."""
    counts: Counter = Counter()
    entries = _move_memberships(organization, source, target, counts)
    parent_ids = {source.parent_id, target.parent_id}
    children = list(OrgUnit.objects.filter(parent=source, is_active=True))
    parent_ids.update(child.parent_id for child in children)
    names = dict(OrgUnit.objects.filter(pk__in=[pk for pk in parent_ids if pk]).values_list("pk", "name"))
    names[source.pk] = source.name
    for child in children:
        child.settings = dict(child.settings or {})
        child.settings.setdefault("history", []).append(_history_entry(child, date, names))
        child.parent = target
        child.save()  # path/level kaskadı
        counts["children_moved"] += 1
        entries.append((child, {"parent": str(source.pk)}, {"parent": str(target.pk)}))

    aliases = set((target.settings or {}).get("aliases") or [])
    wanted = {source.name, *((source.settings or {}).get("aliases") or [])} - {target.name}
    if not wanted <= aliases:
        settings = dict(target.settings or {})
        settings["aliases"] = sorted(aliases | wanted)
        history = settings.setdefault("history", [])
        if not any(entry.get("absorbed_id") == str(source.pk) for entry in history):
            history.append(
                {"date": date, "source": MERGE_SOURCE, "absorbed": source.name, "absorbed_id": str(source.pk)}
            )
        target.settings = settings
        target.save(update_fields=["settings", "updated_at"])
        counts["target_aliases_added"] += len(wanted - aliases)
        entries.append((target, {"aliases": sorted(aliases)}, {"aliases": settings["aliases"]}))

    if _merged_into(source, target) and not source.is_active:
        counts["already_merged"] = 1
    else:
        settings = dict(source.settings or {})
        settings.setdefault("history", []).append(
            {**_history_entry(source, date, names), "merged_into": str(target.pk), "merged_into_name": target.name}
        )
        source.settings = settings
        source.is_active = False
        source.save(update_fields=["settings", "is_active", "updated_at"])
        counts["source_archived"] = 1
        log_action(
            action=AuditAction.UPDATE,
            user=actor,
            organization=organization,
            obj=source,
            reason=reason,
            old_values={"is_active": True},
            new_values={"is_active": False, "merged_into": str(target.pk)},
        )
    if entries:
        log_actions(
            {
                "action": AuditAction.UPDATE,
                "user": actor,
                "organization": organization,
                "obj": obj,
                "reason": reason,
                "old_values": old,
                "new_values": new,
            }
            for obj, old, new in entries
        )
    return counts


__all__ = ["MERGE_SOURCE", "merge_chair_unit", "resolve_merge_units"]
