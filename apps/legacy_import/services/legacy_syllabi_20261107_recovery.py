"""Sahib 2026-11-07: köhnə sillabuslar → jurnala BAĞLI təsdiqli versiya (repo planı), auditli və geri qaytarılan.

* ``restore``: jurnalın öz dosyesi yoxdursa — yeni dosye (``offering`` = jurnal, müəllif = müəllim); varsa — köçürülmüş
  təsdiqli versiya və BOŞ qaralama ARXİVƏ keçir (silinmir), eyni dosyeyə ``approval_source=migration`` ilə yeni
  əsas versiya yazılır. Müəllimin yazdığı qaralama / təqdim / insan təsdiqi varsa hədəf KEÇİLİR (üzərinə yazılmır).
  ``retire_base`` (MR-250): jurnalın əvvəl göstərdiyi səhv baza dosyenin pinlənmiş versiyası da arxivə keçir.
* ``plan_sync``: jurnalın öz təsdiqli dosyesinin ``plan_hours``-u rəsmi yükə (yalnız sütun; bölmələr toxunulmur).

Dərs / xana / qeydiyyat / qiymət toxunulmur (``state.protected`` əvvəl = sonra). Hər yazan icra bir audit qəbzidir
(``lgsyl-…``); ``--undo`` qəbz üzrə hər şeyi qaytarır — yalnız qəbzdən sonra heç nə dəyişməyibsə.
"""

from collections import Counter
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from apps.syllabus.public import (
    import_migrated_version,
    resolve_actor,
    section_data_map,
    services,
    write_version_plan_hours,
)

from . import exact_syllabus_recovery as core
from . import legacy_syllabi_20261107_plan as plan_module
from . import legacy_syllabi_20261107_state as state

RestoreError = core.RestoreError
Skip = state.Skip
RESOURCE = "legacy_import.legacy_syllabi_20261107"
RESTORE_REASON = "2026-11-07 legacy syllabus restore (repo plan)"
UNDO_REASON = "2026-11-07 legacy syllabus undo (repo plan)"
NOTE = (
    "Müəllimin köhnə sistemdəki öz sillabusu bərpa olunub (şəxsi bölmələr — qarşılama, elmi maraq, əlaqə — "
    "köçürülməyib); köhnə sistemin təsdiqi iddia edilmir (sahib 2026-11-07)."
)


def _receipts(org, batch=None):
    logs = core.model("audit.AuditLog").objects.filter(organization=org, resource_type=RESOURCE)
    return logs.filter(resource_id=batch) if batch else logs


def _audit(org, actor, batch, reason, values):
    core.log_action(
        action=core.AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=RESOURCE,
        resource_id=batch,
        resource_repr=batch,
        reason=reason,
        new_values=values,
    )


def _superseded(org, target):
    """Eyni jurnal başqa (köhnə) bərpa əmri ilə artıq yazılıbsa və geri qaytarılmayıbsa — toxunulmur."""
    resource = target.get("skip_if_receipt")
    if not resource:
        return False
    rows = core.model("audit.AuditLog").objects.filter(organization=org, resource_type=resource)
    undone = set(rows.filter(reason__icontains="undo").values_list("resource_id", flat=True))
    return rows.exclude(reason__icontains="undo").exclude(resource_id__in=undone).exists()


def _archive_version(org, actor, version, kind, now):
    if kind == "approved":
        services.archive(version=version, actor=resolve_actor(actor, org))
        return
    updated = (
        core.model("syllabus.SyllabusVersion")
        .objects.filter(pk=version.pk, organization=org, status="draft")
        .update(status="archived", archived_at=now)
    )
    if updated != 1:
        raise RestoreError("blank_draft_changed")


def _restore(org, actor, target, source, offering, counts):
    action, dossier, retire = state.restore_plan(org, target, source, offering)
    if action == "already_ok":
        return "already_ok", None
    base = state.base_to_retire(org, target, offering)
    before = state.protected(org, offering)
    now = timezone.now()
    for version, kind in retire:
        _archive_version(org, actor, version, kind, now)
        counts["versions_archived" if kind == "approved" else "blank_drafts_archived"] += 1
    if dossier is not None:
        kwargs = dict(
            subject=dossier.subject,
            period=dossier.period,
            offering=dossier.offering,
            author=dossier.author,
            chair_unit=dossier.chair_unit,
            program=dossier.program,
        )
        major = 1 + max(
            core.model("syllabus.SyllabusVersion").objects.filter(syllabus=dossier).values_list("major", flat=True)
        )
    else:
        author = core.model("auth.User").objects.get(pk=target["teacher"])
        kwargs = dict(
            subject=offering.subject,
            period=offering.period,
            offering=offering,
            author=author,
            chair_unit=state.chair_for(org, offering, author.pk),
        )
        major = 1
    sections = source["sections"]
    syllabus, version = import_migrated_version(
        organization=org,
        approved_at=now,
        plan_hours=dict(target["plan"]),
        section_data=sections,
        major=major,
        minor=0,
        note=NOTE,
        **kwargs,
    )
    if (dossier is not None and syllabus.pk != dossier.pk) or section_data_map(version) != sections:
        raise RestoreError("import_target_or_content_mismatch")
    syllabus.refresh_from_db()
    shown = state.resolved_for(offering)
    if shown is None or shown.pk != syllabus.pk or shown.approved_version_id != version.pk:
        raise RestoreError("journal_resolution_after_restore")
    if shown.current_version_id != version.pk:
        raise RestoreError("journal_open_version_remains")
    base_row = None
    if base is not None:
        services.archive(version=base, actor=resolve_actor(actor, org))
        base_row = {"syllabus": str(base.syllabus_id), "version": str(base.pk)}
        counts["base_versions_archived"] += 1
    elif target.get("retire_base"):
        counts["base_kept"] += 1
    if state.protected(org, offering) != before:
        raise RestoreError("protected_journal_content_changed")
    counts.update(versions_created=1, topics_restored=len(sections["week"]["rows"]))
    child = {
        "key": target["key"],
        "kind": "restore",
        "offering": str(offering.pk),
        "created": dossier is None,
        "syllabus": str(syllabus.pk),
        "version": str(version.pk),
        "retired": [{"id": str(v.pk), "status": kind} for v, kind in retire],
        "base": base_row,
        "base_after": state.dossier_state(org, base.syllabus) if base is not None else None,
        "content_hash": source["content_sha256"],
        "source_syllabus": int(target["source"]),
        "after": state.dossier_state(org, syllabus),
    }
    return ("created" if dossier is None else "replaced"), child


def _plan_sync(org, target, offering, counts):
    dossier, stale, gap = state.plan_versions(org, target, offering)
    if not stale:
        return "already_ok", None
    rows = []
    for version in stale:
        old = dict(version.plan_hours or {})
        if not write_version_plan_hours(version, target["plan"]):
            raise RestoreError("plan_write_failed")
        rows.append({"id": str(version.pk), "old": old, "new": dict(target["plan"])})
    counts.update(plan_versions_updated=len(rows), week_hours_gap=int(gap))
    child = {
        "key": target["key"],
        "kind": "plan",
        "offering": str(offering.pk),
        "syllabus": str(dossier.pk),
        "versions": rows,
        "after": state.dossier_state(org, dossier),
    }
    return "plan_synced", child


def _process(org, actor, plan, target, counts):
    if _superseded(org, target):
        raise Skip("previously_restored")
    offering = state.offering_scope(org, plan, target)
    if target["action"] == "restore":
        return _restore(org, actor, target, plan["sources"][target["source"]], offering, counts)
    return _plan_sync(org, target, offering, counts)


def actor_scope(org, actor, plan):
    if (
        str(org.pk) != plan["organization_id"]
        or not org.is_active
        or org.status != "active"
        or not actor.is_active
        or not actor.is_superuser
    ):
        raise RestoreError("active_fixed_tenant_superadmin_required")


@transaction.atomic
def apply(org, actor, plan):
    """→ ``(counts, results, batch|None)``; hər hədəf öz savepoint-indədir, keçilən hədəf heç nə yazmır."""
    actor_scope(org, actor, plan)
    counts, results, children = Counter(), [], []
    for target in plan["targets"]:
        counts["targets"] += 1
        local = Counter()
        try:
            with transaction.atomic():
                result, child = _process(org, actor, plan, target, local)
        except Skip as skip:
            result, child, local = f"skipped_{skip.code}", None, Counter()
        except RestoreError as exc:
            result, child, local = f"skipped_{exc}", None, Counter()
        counts.update(local)
        counts[result] += 1
        results.append((target["key"], result))
        if child is not None:
            children.append(child)
    batch = None
    if children:
        batch = f"lgsyl-{timezone.now():%Y%m%d-%H%M%S}-{uuid4().hex[:4]}"
        _audit(
            org,
            actor,
            batch,
            RESTORE_REASON,
            {"plan_sha256": plan_module.PLAN_SHA256, "legacy_approval_asserted": False, "children": children},
        )
    return dict(counts), results, batch


def _check_child(org, child):
    syllabus = core.model("syllabus.Syllabus").objects.select_for_update().get(pk=child["syllabus"], organization=org)
    if state.dossier_state(org, syllabus) != child["after"]:
        raise RestoreError("undo_live_state_changed")
    if child["kind"] == "restore":
        version = core.model("syllabus.SyllabusVersion").objects.get(pk=child["version"], syllabus=syllabus)
        if version.status != "approved" or state.links(org, syllabus):
            raise RestoreError("undo_live_state_changed")
    if child.get("base"):
        base = core.model("syllabus.Syllabus").objects.select_for_update().get(pk=child["base"]["syllabus"])
        if state.dossier_state(org, base) != child["base_after"]:
            raise RestoreError("undo_live_state_changed")
    return syllabus


def _undo_child(org, actor, child, syllabus):
    Version = core.model("syllabus.SyllabusVersion")
    if child["kind"] == "plan":
        for row in child["versions"]:
            version = Version.objects.get(pk=row["id"], syllabus=syllabus)
            if plan_module.plan_of(row["old"]) and write_version_plan_hours(version, row["old"]):
                continue
            Version.objects.filter(pk=version.pk).update(plan_hours=row["old"])
        return Counter(plans_restored=1)
    services.archive(version=Version.objects.get(pk=child["version"]), actor=resolve_actor(actor, org))
    for item in child["retired"]:
        restored = Version.objects.filter(pk=item["id"], syllabus=syllabus, status="archived").update(
            status=item["status"], archived_at=None
        )
        if restored != 1:
            raise RestoreError("undo_retired_version_changed")
    services.refresh_pointers(syllabus)
    if child["created"]:
        syllabus.is_active = False
        syllabus.save(update_fields=["is_active", "updated_at"])
    counts = Counter(
        versions_archived=1, versions_restored=len(child["retired"]), syllabi_retired=int(child["created"])
    )
    if child.get("base"):
        base = core.model("syllabus.Syllabus").objects.get(pk=child["base"]["syllabus"])
        if Version.objects.filter(pk=child["base"]["version"], syllabus=base, status="archived").update(
            status="approved", archived_at=None
        ):
            services.refresh_pointers(base)
            counts["base_versions_restored"] += 1
        else:
            raise RestoreError("undo_retired_version_changed")
    return counts


@transaction.atomic
def undo(org, actor, batch, plan):
    actor_scope(org, actor, plan)
    logs = _receipts(org, batch)
    if logs.filter(reason=UNDO_REASON).exists():
        return {"already_undone": 1}
    receipt = logs.filter(reason=RESTORE_REASON).first()
    if receipt is None:
        raise RestoreError("undo_batch_missing")
    children = receipt.new_values["children"]
    checked = [(child, _check_child(org, child)) for child in children]
    counts = Counter()
    for child, syllabus in reversed(checked):
        counts.update(_undo_child(org, actor, child, syllabus))
    _audit(org, actor, batch, UNDO_REASON, {"receipt": str(receipt.pk)})
    return dict(counts)
