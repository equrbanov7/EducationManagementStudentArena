"""Separate fixed append, preserving the human draft and every existing journal cell."""

from uuid import uuid4

from django.utils import timezone

from apps.audit.public import log_action
from apps.syllabus.public import import_migrated_version, resolve_actor, section_data_map, services
from core.constants import AuditAction

from . import blank_draft_syllabus_spec as spec
from . import blank_draft_syllabus_state as state
from . import exact_syllabus_recovery as core
from .blank_draft_syllabus_source import load  # noqa: F401

RestoreError = core.RestoreError
RESOURCE = "legacy_import.blank_draft_source_syllabi"


def receipts(org, batch=None, kind="apply"):
    qs = core.model("audit.AuditLog").objects.filter(organization=org, resource_type=RESOURCE, new_values__kind=kind)
    return qs.filter(resource_id=str(batch)) if batch else qs


def audit(org, actor, batch, values):
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=RESOURCE,
        resource_id=str(batch),
        resource_repr=str(batch),
        reason="Reviewed own-source version beside preserved empty draft",
        new_values=values,
    )


def _capture(org, actor, previous=None, undone=False):
    states, objects = {}, []
    children = {r["offering_id"]: r for r in previous["children"]} if previous else {}
    for row in spec.ROWS:
        child = children.get(row["offering_id"])
        snapshot, syllabus, draft = state.capture(
            org, actor, row, source_version_id=child["source_version_id"] if child else None, undone=undone
        )
        states[row["offering_id"]] = snapshot
        objects.append((row, syllabus, draft))
    return states, objects


def run(org, actor, loaded=None, *, expected_baseline="", apply=False, undo=""):
    state.actor_scope(org, actor)
    if not spec.ROWS:
        raise RestoreError("fixed_cases_required")
    if undo:
        receipt = receipts(org, undo).select_for_update().first()
        if receipt is None:
            raise RestoreError("reviewed_apply_receipt_missing")
    else:
        receipt = receipts(org).order_by("created_at", "pk").last()
    previous = receipt.new_values if receipt else None
    undone_receipt = (
        receipts(org, receipt.resource_id, kind="undo").order_by("created_at", "pk").last() if receipt else None
    )
    if previous and (
        previous.get("source_sha256") != spec.ROWS[0]["packet_sha256"]
        or [c["offering_id"] for c in previous["children"]] != [r["offering_id"] for r in spec.ROWS]
    ):
        raise RestoreError("reviewed_receipt_source_scope_changed")
    before, objects = _capture(org, actor, previous, undone=bool(undone_receipt))
    baseline = core.digest(before)
    if (apply and not expected_baseline) or (expected_baseline and expected_baseline != baseline):
        raise RestoreError("fresh_baseline_required")
    counts = {
        "cases": len(spec.ROWS),
        "human_drafts_preserved": len(spec.ROWS),
        "versions_created": 0,
        "versions_archived": 0,
    }
    if previous:
        expected = undone_receipt.new_values["after"] if undone_receipt else previous["after"]
        if before != expected:
            raise RestoreError("current_post_restore_graph_changed")
        if not undo:
            if undone_receipt:
                raise RestoreError("previous_undo_requires_review")
            return {
                "status": "already_present",
                "baseline": baseline,
                "after_baseline": baseline,
                "receipt": str(receipt.resource_id),
                **counts,
            }
        if undone_receipt:
            return {
                "status": "already_undone",
                "baseline": baseline,
                "after_baseline": baseline,
                "receipt": str(receipt.resource_id),
                **counts,
            }
    if not apply:
        return {
            "status": "dry_run",
            "baseline": baseline,
            "receipt": str(receipt.resource_id) if receipt else None,
            **counts,
        }
    if undo:
        for child in previous["children"]:
            version = (
                core.model("syllabus.SyllabusVersion")
                .objects.select_for_update()
                .get(pk=child["source_version_id"], organization=org)
            )
            services.archive(version=version, actor=resolve_actor(actor, org))
        after, _ = _capture(org, actor, previous, undone=True)
        for key in before:
            if before[key]["protected"] != after[key]["protected"]:
                raise RestoreError("protected_journal_content_changed")
        audit(
            org,
            actor,
            undo,
            {"kind": "undo", "source_sha256": previous["source_sha256"], "after": after, "original": str(receipt.pk)},
        )
        counts["versions_archived"] = len(spec.ROWS)
        return {
            "status": "undone",
            "baseline": baseline,
            "after_baseline": core.digest(after),
            "receipt": str(undo),
            **counts,
        }
    if loaded is None or [r[0]["offering_id"] for r in loaded] != [r["offering_id"] for r in spec.ROWS]:
        raise RestoreError("fixed_loaded_cases_required")
    children = []
    for (row, syllabus, draft), (_, sections, codes) in zip(objects, loaded):
        _, version = import_migrated_version(
            organization=org,
            subject=syllabus.subject,
            offering=syllabus.offering,
            period=syllabus.period,
            author=syllabus.author,
            chair_unit=syllabus.chair_unit,
            program=syllabus.program,
            major=draft.major,
            minor=draft.minor + 1,
            approved_at=timezone.now(),
            plan_hours=dict(zip(("lecture", "seminar", "practical", "lab"), row["contact_hours"])),
            section_data=sections,
            note="Reviewed current migration approval of the teacher's exact own source; legacy approval is not asserted. Human draft remains unchanged.",
        )
        if section_data_map(version) != sections:
            raise RestoreError("source_import_content_mismatch")
        children.append(
            {
                "offering_id": row["offering_id"],
                "source_version_id": str(version.pk),
                "source_syllabus": row["source_syllabus"],
                "human_draft_id": str(draft.pk),
                "conversion_codes": list(codes),
            }
        )
    manifest = {"kind": "apply", "source_sha256": spec.ROWS[0]["packet_sha256"], "children": children}
    after, _ = _capture(org, actor, manifest)
    if any(before[key]["protected"] != after[key]["protected"] for key in before):
        raise RestoreError("protected_journal_content_changed")
    manifest.update(before=before, after=after, legacy_approval_asserted=False)
    batch = str(uuid4())
    audit(org, actor, batch, manifest)
    counts["versions_created"] = len(spec.ROWS)
    return {"status": "applied", "baseline": baseline, "after_baseline": core.digest(after), "receipt": batch, **counts}
