"""One fixed bank: four genuine own BASE dossiers, five current courses, no academic edits."""

import uuid
from collections import Counter

from django.db import transaction
from django.utils import timezone

from apps.audit.public import log_action
from apps.syllabus.public import import_migrated_version, link_legacy_share, resolve_actor, section_data_map, services
from core.constants import AuditAction

from . import exact_syllabus_recovery as core
from . import own_base_syllabus_spec as spec
from . import own_base_syllabus_state as state
from .own_base_syllabus_source import load, require  # noqa: F401


def audit(org, actor, receipt, values, batch):
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=spec.RESOURCE + "." + batch,
        resource_id=receipt,
        resource_repr=receipt,
        reason=spec.NOTE,
        new_values=values,
    )


def result(status, snapshot, baseline, receipt=None, counts=None):
    return {
        "status": status,
        "baseline": baseline,
        "receipt": receipt,
        "cases": len(snapshot["dispositions"]),
        "versions_created": (counts or {}).get("versions_created", 0),
        "shares_created": (counts or {}).get("shares_created", 0),
        "skip_approved": sum(v == "skip_approved" for v in snapshot["dispositions"].values()),
        "skip_existing": sum(v == "skip_existing" for v in snapshot["dispositions"].values()),
        "ready": sum(v == "ready" for v in snapshot["dispositions"].values()),
        "protected_graph": core.digest(snapshot["protected"]),
    }


@transaction.atomic
def run(*, organization, actor, loaded=None, apply=False, expected_baseline="", undo="", batch="all"):
    require(batch in ("all", "ordinary", "design"), "fixed_batch_required")
    source_ids = {7121, 8839} if batch == "ordinary" else {4164, 8473}
    rows = spec.ROWS if batch == "all" else tuple(r for r in spec.ROWS if r["source_id"] in source_ids)
    if batch != "all":
        require(len(rows) == (2 if batch == "ordinary" else 3), "fixed_batch_targets_changed")
    org = organization
    state.actor_scope(org, actor)
    records = core.model("audit.AuditLog").objects.filter(organization=org, resource_type=spec.RESOURCE + "." + batch)
    previous = records.filter(new_values__operation="apply").order_by("-created_at", "pk").first()
    values = previous.new_values if previous else None
    receipt = str(previous.resource_id) if previous else None
    if undo:
        require(receipt == undo, "exact_undo_receipt_required")
    undone = records.filter(new_values__operation="undo", new_values__undo_of=receipt).first() if receipt else None
    before, objects = state.snapshot(
        org, actor, children=values["children"] if values else (), shares=values["shares"] if values else (), rows=rows
    )
    baseline = core.digest(before)
    if expected_baseline:
        require(expected_baseline == baseline, "fresh_baseline_required")
    if apply:
        require(bool(expected_baseline), "fresh_baseline_required")
    if previous:
        require(values["source_sha256"] == spec.SOURCE_SHA, "receipt_source_changed")
        require(before == (undone.new_values["after"] if undone else values["after"]), "post_restore_graph_changed")
        if undone:
            require(bool(undo), "archived_previous_recovery_requires_review")
            return result("already_undone", before, baseline, receipt)
        if not undo:
            return result("already_present", before, baseline, receipt)
    if not apply:
        return result("dry_run", before, baseline, receipt)
    if undo:
        for item in values["shares"]:
            share = (
                core.model("syllabus.SyllabusShare").objects.select_for_update().get(pk=item["id"], organization=org)
            )
            require(core.metadata_digest(share) == item["metadata"], "created_share_changed")
            # Only the exact newly-created share is removed; every pre-existing share stays untouched.
            share.delete()
        for child in values["children"]:
            syllabus = (
                core.model("syllabus.Syllabus").objects.select_for_update().get(pk=child["syllabus"], organization=org)
            )
            version = (
                core.model("syllabus.SyllabusVersion")
                .objects.select_for_update()
                .get(pk=child["version"], organization=org, syllabus=syllabus)
            )
            require(core.digest(section_data_map(version)) == child["body"], "created_source_body_changed")
            services.archive(version=version, actor=resolve_actor(actor, org))
            syllabus.is_active = False
            syllabus.save(update_fields=["is_active", "updated_at"])
        after, _ = state.snapshot(org, actor, children=values["children"], shares=(), rows=rows)
        require(before["protected"] == after["protected"], "academic_graph_changed")
        audit(
            org,
            actor,
            receipt,
            dict(operation="undo", undo_of=receipt, after=after, removed_shares=values["shares"]),
            batch,
        )
        return result("undone", after, core.digest(after), receipt)
    require(loaded is not None and set(loaded) == {r["offering_id"] for r in spec.ROWS}, "fixed_loaded_source_set")
    for row in spec.ROWS:
        sections, _, original_digest = loaded[row["offering_id"]]
        require(
            core.digest(sections) == row["body_digest"] and original_digest == row["original_body_digest"],
            "loaded_source_changed",
        )
    children, shares, anchors, counts = [], [], {}, Counter()
    for row, obj in zip(rows, objects):
        if before["dispositions"][str(obj.pk)] != "ready":
            continue
        source_key = (row["source_id"], row["teacher_id"], row["subject_id"])
        if source_key in anchors:
            primary = anchors[source_key]
            outcome = link_legacy_share(syllabus=primary, offering=obj, user=actor)
            require(outcome == "linked", "fixed_sibling_share_failed_" + outcome)
            share = (
                core.model("syllabus.SyllabusShare")
                .objects.select_for_update()
                .get(organization=org, syllabus=primary, offering=obj)
            )
            shares.append({"id": str(share.pk), "offering": str(obj.pk), "metadata": core.metadata_digest(share)})
            counts["shares_created"] += 1
            continue
        sections, _, _ = loaded[str(obj.pk)]
        syllabus, version = import_migrated_version(
            organization=org,
            subject=obj.subject,
            offering=obj,
            period=obj.period,
            author=obj.restoration_author,
            chair_unit=obj.subject.chair_unit,
            approved_at=timezone.now(),
            plan_hours=dict(zip(("lecture", "seminar", "practical", "lab"), row["contact_hours"])),
            section_data=sections,
            note=spec.NOTE,
        )
        require(section_data_map(version) == sections, "source_import_changed")
        children.append(state.created_child(org, obj, syllabus, version))
        anchors[source_key] = syllabus
        counts["versions_created"] += 1
    after, _ = state.snapshot(org, actor, children=children, shares=shares, rows=rows)
    require(before["protected"] == after["protected"], "academic_graph_changed")
    receipt = str(uuid.uuid4())
    audit(
        org,
        actor,
        receipt,
        dict(
            operation="apply",
            source_sha256=spec.SOURCE_SHA,
            before=before,
            after=after,
            children=children,
            shares=shares,
            legacy_approval_asserted=False,
            raw_legacy_status={str(r["source_id"]): 0 for r in spec.ROWS},
            current_approval_authority="explicit_user_reviewed_own_active_base_recovery",
            source_journal_pointer_asserted=False,
            source_kind_hours={str(r["source_id"]): r["source_contact_hours"] for r in spec.ROWS},
            official_kind_hours={r["offering_id"]: r["contact_hours"] for r in spec.ROWS},
            source_body_hashes={
                str(r["source_id"]): {
                    "raw": r["source_digest"],
                    "converted": r["original_body_digest"],
                    "visible": r["body_digest"],
                }
                for r in spec.ROWS
            },
        ),
        batch,
    )
    return result("applied", before, baseline, receipt, counts)
