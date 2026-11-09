"""Atomic reviewed writes and stale-graph guarded, history-preserving undo."""

from collections import Counter
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from apps.audit.public import log_action
from apps.registrar.public import journal_access_diagnostics, plan_hours_for_offering
from apps.syllabus.public import (
    approved_version_for,
    import_migrated_version,
    link_carry_share,
    publish_reviewed_draft,
    resolve_actor,
    reviewed_batch_without_carry,
    section_data_map,
    services,
    unlink_carry_share,
    write_version_plan_hours,
)
from core.constants import AuditAction

from . import plan, state
from .contracts import RESOURCE, RestoreError, actor_scope, digest, hours, model, selected_ids


def receipts(org, *, batch=None, key=None, kind="apply"):
    query = model("audit.AuditLog").objects.filter(organization=org, resource_type=RESOURCE, new_values__kind=kind)
    if batch:
        query = query.filter(resource_id=str(batch))
    if key:
        query = query.filter(new_values__operation_key=key)
    return query.order_by("created_at", "pk")


def record(org, actor, batch, values):
    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=org,
        resource_type=RESOURCE,
        resource_id=str(batch),
        resource_repr=str(batch),
        reason="Reviewed 2026-11-09 syllabus remediation",
        new_values=values,
    )


def _version(org, pk):
    return (
        model("syllabus.SyllabusVersion")
        .objects.select_related("syllabus", "organization")
        .get(organization=org, pk=pk)
    )


def _write(org, actor, action, offering):
    kind = action["action"]
    if kind == "carry":
        donor = model("syllabus.Syllabus").objects.get(organization=org, pk=action["donor_id"])
        code, share = link_carry_share(syllabus=donor, offering=offering, user=actor)
        if code != "linked" or share is None:
            raise RestoreError("reviewed_carry_target_changed")
        return
    if kind == "plan_hours":
        if not write_version_plan_hours(_version(org, action["version_id"]), action["official_hours"]):
            raise RestoreError("reviewed_plan_write_refused")
        return
    if kind == "publish":
        version = _version(org, action["version_id"])
        write_version_plan_hours(version, action["official_hours"])
        for section in version.sections.all():
            proposed = action["sections"].get(section.section_id, section.data)
            if section.data != proposed:
                model("syllabus.SyllabusSection").objects.filter(pk=section.pk, organization=org).update(
                    data=proposed, revision=section.revision + 1, updated_by=actor, updated_at=timezone.now()
                )
        version.refresh_from_db()
        publish_reviewed_draft(
            version=version,
            actor=resolve_actor(actor, org),
            expected_body_sha256=action["body_sha256"],
            reason="Owner-authorized audit publication; teacher-authored content preserved.",
        )
        return
    if kind != "restore":
        raise RestoreError("unreviewed_action")
    dossier = None
    if action["syllabus_id"]:
        dossier = model("syllabus.Syllabus").objects.get(pk=action["syllabus_id"], organization=org)
        if dossier.offering_id != offering.pk:
            raise RestoreError("restore_requires_owned_dossier")
        for old in dossier.versions.filter(status__in=("approved", "draft", "revision")):
            if old.status == "approved":
                services.archive(version=old, actor=resolve_actor(actor, org))
            else:
                model("syllabus.SyllabusVersion").objects.filter(pk=old.pk).update(
                    status="archived", archived_at=timezone.now()
                )
        if action.get("rebind_subject"):
            model("syllabus.Syllabus").objects.filter(pk=dossier.pk, organization=org).update(
                subject=offering.subject, period=offering.period
            )
            dossier.refresh_from_db()
    largest = dossier.versions.order_by("-major").values_list("major", flat=True).first() if dossier else 0
    _dossier, version = import_migrated_version(
        organization=org,
        subject=offering.subject,
        offering=offering,
        period=dossier.period if dossier else offering.period,
        author=offering.instructor,
        chair_unit=dossier.chair_unit if dossier else offering.subject.chair_unit,
        program=dossier.program if dossier else None,
        major=(largest or 0) + 1,
        approved_at=timezone.now(),
        plan_hours=action["official_hours"],
        section_data=action["sections"],
        note="Current owner-authorized exact legacy restoration; original draft retained in history. Historical human approval is not asserted.",
    )
    if digest(section_data_map(version)) != digest(action["sections"]):
        raise RestoreError("restored_body_mismatch")


def _postconditions(offerings, actions):
    target_ids = {oid for row in actions for oid in row.get("affected_offering_ids", [row["offering_id"]])}
    results = []
    for offering in offerings:
        if str(offering.pk) not in target_ids:
            continue
        selected = state.resolved(offering)
        version = approved_version_for(selected)
        if selected is None or version is None or selected.subject_id != offering.subject_id:
            raise RestoreError("approved_current_subject_postcondition_failed")
        if selected.period_id not in (None, offering.period_id):
            raise RestoreError("approved_current_period_postcondition_failed")
        if (
            model("syllabus.SyllabusVersion")
            .objects.filter(syllabus=selected, status__in=("draft", "revision"))
            .exists()
        ):
            raise RestoreError("current_draft_still_open")
        current_hours = hours(plan_hours_for_offering(offering))
        plan.checked_content(section_data_map(version), current_hours)
        diagnostics = journal_access_diagnostics(offering=offering, teacher_ids=[offering.instructor_id])
        if len(diagnostics) != 1 or diagnostics[0]["blocker_codes"] or not diagnostics[0]["user_grade_input"]:
            raise RestoreError("teacher_journal_structural_access_failed")
        results.append(
            {
                "offering_id": str(offering.pk),
                "version_id": str(version.pk),
                "teacher_structural_editor": True,
                "approved_syllabus_unlocked": True,
                "runtime_write_verified": False,
                "unknown_codes": diagnostics[0]["unknown_codes"],
            }
        )
    return results


def _baseline(graph, actions, held, packet):
    return digest({"graph": graph, "actions": actions, "held": held, "packet": packet.get("sha256")})


@transaction.atomic
def run(org, actor, *, packet=None, offering_ids=(), apply=False, expected_baseline="", undo=""):
    actor_scope(org, actor)
    packet = packet or {"sources": {}, "bindings": {}, "sha256": None}
    if undo:
        return undo_receipt(org, actor, undo, apply=apply, expected_baseline=expected_baseline)
    ids = selected_ids(offering_ids)
    if apply and len(ids) > 100:
        raise RestoreError("bounded_apply_max100_targets")
    graph, offerings = state.capture(org, ids, lock=apply)
    key = digest({"ids": ids, "packet": packet.get("sha256")})
    previous = receipts(org, key=key).last()
    if previous:
        if receipts(org, batch=previous.resource_id, kind="undo").exists():
            raise RestoreError("previous_undo_requires_new_review")
        if graph != previous.new_values["after"]:
            raise RestoreError("existing_repair_graph_changed")
        return {
            "status": "already_present",
            "receipt": str(previous.resource_id),
            "baseline": digest(graph),
            "actions": [],
            "held": [],
        }
    actions, held = plan.prepare(offerings, packet, ids)
    baseline = _baseline(graph, actions, held, packet)
    if (apply and not expected_baseline) or (expected_baseline and expected_baseline != baseline):
        raise RestoreError("fresh_baseline_required")
    result = {
        "status": "dry_run",
        "baseline": baseline,
        "receipt": None,
        "counts": dict(Counter(row["action"] for row in actions)),
        "actions": plan.safe_actions(actions),
        "held": held,
    }
    if not apply or not actions:
        if apply:
            result["status"] = "no_verified_actions"
        return result
    by_id = {str(o.pk): o for o in offerings}
    with reviewed_batch_without_carry():
        for action in actions:
            _write(org, actor, action, by_id[action["offering_id"]])
    postconditions = _postconditions(offerings, actions)
    after, _ = state.capture(org, ids)
    if graph["protected"] != after["protected"] or graph["context"] != after["context"]:
        raise RestoreError("protected_academic_or_source_context_changed")
    batch = str(uuid4())
    record(
        org,
        actor,
        batch,
        {
            "kind": "apply",
            "operation_key": key,
            "scope_ids": list(ids),
            "source_packet_sha256": packet.get("sha256"),
            "before": graph,
            "after": after,
            "actions": plan.safe_actions(actions),
            "postconditions": postconditions,
        },
    )
    return {
        **result,
        "status": "applied",
        "receipt": batch,
        "after_baseline": digest(after),
        "postconditions": postconditions,
    }


def _restore_table(org, label, before, after):
    after_map = {row["id"]: row for row in after}
    for row in before:
        if row != after_map.get(row["id"]):
            model(label).objects.filter(pk=row["id"], organization=org).update(
                **{k: v for k, v in row.items() if k != "id"}
            )


def undo_receipt(org, actor, batch, *, apply, expected_baseline):
    query = receipts(org, batch=batch)
    receipt = (query.select_for_update() if apply else query).last()
    if receipt is None:
        raise RestoreError("reviewed_apply_receipt_missing")
    prior = receipt.new_values
    ids = selected_ids(prior["scope_ids"])
    current, _ = state.capture(org, ids, lock=apply)
    undone = receipts(org, batch=batch, kind="undo").last()
    expected = undone.new_values["after"] if undone else prior["after"]
    if current != expected:
        raise RestoreError("undo_live_graph_changed")
    baseline = digest(current)
    if (apply and not expected_baseline) or (expected_baseline and expected_baseline != baseline):
        raise RestoreError("fresh_baseline_required")
    result = {
        "status": "already_undone" if undone else "dry_run",
        "baseline": baseline,
        "receipt": str(batch),
        "actions": [],
        "held": [],
    }
    if undone or not apply:
        return result
    before, after = prior["before"], prior["after"]
    old_versions = {r["id"] for r in before["versions"]}
    changed_versions = {r["id"] for r in after["versions"] if r not in before["versions"]}
    model("syllabus.SyllabusVersion").objects.filter(
        organization=org, pk__in=changed_versions, status__in=("approved", "draft", "revision")
    ).update(status="archived", archived_at=timezone.now())
    with reviewed_batch_without_carry():
        for share in after["shares"]:
            if share["id"] not in {r["id"] for r in before["shares"]}:
                if not unlink_carry_share(share_id=share["id"], organization=org, user=actor):
                    raise RestoreError("undo_created_share_changed")
        _restore_table(org, "syllabus.SyllabusVersion", before["versions"], after["versions"])
        _restore_table(org, "syllabus.SyllabusSection", before["sections"], after["sections"])
        _restore_table(org, "syllabus.Syllabus", before["syllabi"], after["syllabi"])
        new_syllabi = {r["id"] for r in after["syllabi"]} - {r["id"] for r in before["syllabi"]}
        model("syllabus.Syllabus").objects.filter(organization=org, pk__in=new_syllabi).update(
            is_active=False, approved_version=None
        )
    if model("syllabus.SyllabusVersion").objects.filter(organization=org, pk__in=old_versions).count() != len(
        old_versions
    ):
        raise RestoreError("undo_history_missing")
    restored, _ = state.capture(org, ids)
    if restored["protected"] != current["protected"]:
        raise RestoreError("undo_protected_academic_changed")
    record(org, actor, batch, {"kind": "undo", "original_receipt_id": str(receipt.pk), "after": restored})
    return {**result, "status": "undone", "after_baseline": digest(restored)}
