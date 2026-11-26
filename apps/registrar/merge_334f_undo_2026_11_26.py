"""``merge_334f_journals_20261126 --undo --batch m334f-…`` — :mod:`.merge_334f_2026_11_26` qaçışının geri qaytarılması.

YALNIZ həmin ``batch``-ın audit sətirləri əsasında, tərs ardıcıllıqla:

1. hər birləşmiş ailə — 2026-11-08 geri qaytarıcısı (:func:`.subgroup_journal_merge_undo_2026_11_08._undo_family`):
   kopyalanmış xana / bal / dərs / qeydiyyat / seminar alt qrupu / slot / yük sətrinə əlavə olunan ana qrup silinir,
   alt qrup jurnalları və qeydiyyatları yenidən aktiv, yaradılmış «334F» jurnalı passiv. Birləşmədən SONRA «334F»
   jurnalında yeni data yaranıbsa ailəyə toxunulmur (``undo_blocked_post_merge_data``); təkrar qaçışda yenidən aktiv
   edilmiş jurnal yenidən passiv olur;
2. bütün ailələr geri qayıdıbsa — alt qrupların ``settings.parent_group`` izi əvvəlki dəyərinə; bu qaçışın yaratdığı
   (və ya yenidən aktiv etdiyi) «334F» qrupu ARXİVƏ (``is_active=False``) — yalnız onun başqa aktiv jurnalı və
   tələbəsi yoxdursa (``undo_parent_kept_in_use``).

İkinci geri qaytarma heç nə etmir (``undo_already_done``).
"""

from __future__ import annotations

from collections import Counter

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

from .merge_334f_2026_11_26 import RESOURCE, UNDO_REASON
from .subgroup_journal_merge_undo_2026_11_08 import _post_merge_data, _undo_family


def _model(name: str, app: str = "registrar"):
    return django_apps.get_model(app, name)


def _undo_families(organization, actor, counts, rows, batch) -> bool:
    """Qaytarır: hər ailə geri qayıdıbmı (ana qrup bağını sökmək olarmı)."""
    CourseOffering = _model("CourseOffering")
    clean = True
    for row in reversed(rows):
        manifest = (row.changes or {}).get("manifest") or {}
        target_id = (row.changes or {}).get("target")
        retired = manifest.get("sources_retired") or []
        if not retired:
            continue
        if CourseOffering.objects.filter(pk__in=retired, is_active=True).exists():
            counts["undo_family_already_done"] += 1
            continue
        if _post_merge_data(target_id, row.created_at, manifest):
            counts["undo_blocked_post_merge_data"] += 1
            clean = False
            continue
        with transaction.atomic():
            _undo_family(
                organization,
                actor,
                counts,
                manifest,
                target_id,
                audit={
                    "reason": UNDO_REASON,
                    "resource_type": f"{RESOURCE}.undo",
                    "new_values": {"batch": batch, "op": "family"},
                },
            )
            revived = str((row.new_values or {}).get("revived_target") or "")
            if revived:
                counts["undo_targets_deactivated"] += CourseOffering.objects.filter(
                    pk=revived, is_active=True, enrollments__isnull=True
                ).update(is_active=False, updated_at=timezone.now())
    return clean


def _undo_parent(organization, counts, values) -> None:
    OrgUnit = _model("OrgUnit", "organizations")
    parent_id = values.get("parent")
    for unit_id, old in values.get("linked") or []:
        unit = OrgUnit.objects.select_for_update().filter(organization=organization, pk=unit_id).first()
        blob = dict(unit.settings) if unit is not None and isinstance(unit.settings, dict) else None
        if blob is None or str(blob.get("parent_group") or "") != str(parent_id):
            counts["undo_link_changed_kept"] += 1
            continue
        if old:
            blob["parent_group"] = old
        else:
            blob.pop("parent_group", None)
        unit.settings = blob
        unit.save(update_fields=["settings", "updated_at"])
        counts["undo_links_removed"] += 1
    own = values.get("created") or values.get("revived")
    if not own:
        return
    in_use = (
        _model("CourseOffering").objects.filter(group_id=own, is_active=True).exists()
        or _model("StudentAcademicRecord").objects.filter(group_id=own, is_active=True).exists()
    )
    if in_use:
        counts["undo_parent_kept_in_use"] += 1
        return
    counts["undo_parent_archived"] += OrgUnit.objects.filter(pk=own, is_active=True).update(
        is_active=False, updated_at=timezone.now()
    )


def undo(*, organization, actor, counts: Counter, batch: str) -> None:
    AuditLog = _model("AuditLog", "audit")
    done = AuditLog.objects.filter(
        organization=organization, resource_type=f"{RESOURCE}.undo", new_values__batch=batch, new_values__op="batch"
    )
    if done.exists():
        counts["undo_already_done"] += 1
        return
    rows = list(
        AuditLog.objects.filter(organization=organization, resource_type=RESOURCE, new_values__batch=batch).order_by(
            "created_at"
        )
    )
    if not rows:
        counts["undo_batch_unknown"] += 1
        return
    families = [row for row in rows if (row.new_values or {}).get("op") == "family"]
    parents = [row.new_values for row in rows if (row.new_values or {}).get("op") == "parent"]
    clean = _undo_families(organization, actor, counts, families, batch)
    if clean:
        for values in parents:
            _undo_parent(organization, counts, values)
    else:
        counts["undo_parent_kept_merged_family"] += len(parents)
    if not clean:
        return  # bloklanmış ailə qalır — partiya «tamamlanmış» sayılmır, sonra yenidən cəhd oluna bilər
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        reason=UNDO_REASON,
        resource_type=f"{RESOURCE}.undo",
        resource_id=batch,
        resource_repr="334F birləşməsi geri qaytarıldı",
        old_values={},
        new_values={"batch": batch, "op": "batch", "families": len(families)},
    )


__all__ = ["undo"]
