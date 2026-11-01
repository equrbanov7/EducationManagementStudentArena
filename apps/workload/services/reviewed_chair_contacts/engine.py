"""Four exact source-corroborated corrections; atomic dry/apply and receipt-bound undo."""

import uuid

from django.db import connection, transaction

from core.audit import log_action
from core.constants import AuditAction

from ..sbio235_state import RepairError, digest, model
from . import actions, retained_rights, spec, state


def _same(old, new, allowed, code):
    if {k: v for k, v in old.items() if k not in allowed} != {k: v for k, v in new.items() if k not in allowed}:
        raise RepairError(code)


def preserved(cases, before, after):
    for name in (
        "protected",
        "groups",
        "memberships",
        "teacher_profiles",
        "roles",
        "handovers",
        "selected_syllabus_ids",
        "selection_sha256",
        "impact",
        "share_rows",
    ):
        if before[name] != after[name]:
            raise RepairError("preservation_failed_" + name)
    for name, fields in {
        "rows": {*next(iter(state.flat(cases, "rows").values()))["old"], "updated_at"},
        "tasks": {"status", "updated_at"},
        "offerings": {"instructor_id", "lesson_hours", "updated_at"},
    }.items():
        current = {r["id"]: r for r in after[name]}
        if set(current) != {r["id"] for r in before[name]}:
            raise RepairError("existing_" + name + "_missing")
        for old in before[name]:
            _same(old, current[old["id"]], fields, "unrelated_" + name + "_changed")
    for name, allowed in (("syllabi", {"plan_hours_override"}), ("versions", {"plan_hours"})):
        current = {r["id"]: r for r in after[name]}
        if set(current) != {r["id"] for r in before[name]}:
            raise RepairError("syllabus_closure_changed")
        for old in before[name]:
            selected = (
                old["id"] in before["selected_syllabus_ids"]
                if name == "syllabi"
                else old["syllabus_id"] in before["selected_syllabus_ids"] and old["status"] != "archived"
            )
            _same(old, current[old["id"]], allowed if selected else set(), "syllabus_content_or_authorship_changed")
    amendment_rows = {a["id"]: a for a in after["amendments"]}
    old_ids = {a["id"] for a in before["amendments"]}
    if any(amendment_rows.get(a["id"]) != a for a in before["amendments"]):
        raise RepairError("existing_amendment_history_changed")
    if any(a["target_id"] not in state.flat(cases, "rows") for pk, a in amendment_rows.items() if pk not in old_ids):
        raise RepairError("outside_row_amendment_created")
    old_manual = [r for r in before["shares"] if r["source"] != "workload"]
    new_manual = [r for r in after["shares"] if r["source"] != "workload"]
    if old_manual != new_manual:
        raise RepairError("manual_journal_scope_changed")
    assignments = {a["id"]: a for a in after["assignments"]}
    deleted = {a["id"] for row in state.flat(cases, "rows").values() for a in row["assignments"] if a["new"] is None}
    for old in before["assignments"]:
        if old["id"] not in assignments:
            if old["id"] not in deleted:
                raise RepairError("unreviewed_assignment_deleted")
            continue
        _same(
            old,
            assignments[old["id"]],
            {"teacher_id", "hours", "is_hourly_paid", "assigned_by_id", "updated_at"},
            "assignment_identity_or_notes_changed",
        )


def desired(cases, current):
    assignments = {a["id"]: a for a in current["assignments"]}
    expected = {a["id"]: a["new"] for p in state.flat(cases, "rows").values() for a in p["assignments"] if a["new"]}
    if set(assignments) != set(expected):
        return False
    if any(any(assignments[pk][k] != v for k, v in value.items()) for pk, value in expected.items()):
        return False
    if any(
        any(row[k] != value for k, value in state.flat(cases, "rows")[row["id"]]["new"].items())
        for row in current["rows"]
    ):
        return False
    for offering in current["offerings"]:
        pin = state.flat(cases, "offerings")[offering["id"]]
        if (offering["instructor_id"], offering["lesson_hours"]) != (pin["new_owner"], pin["new_hours"]):
            return False
    for case in cases.values():
        ids = {s["id"] for s in current["syllabi"] if s["offering_id"] in case["offerings"] and s["is_active"]}
        if any(
            state._hours(s["plan_hours_override"]) != state._hours(case["plan_hours"])
            for s in current["syllabi"]
            if s["id"] in ids
        ):
            return False
        if any(
            state._hours(v["plan_hours"]) != state._hours(case["plan_hours"])
            for v in current["versions"]
            if v["syllabus_id"] in ids and v["status"] != "archived"
        ):
            return False
        for pk, pin in case["offerings"].items():
            teacher_kinds = {}
            for row in case["rows"]:
                if pin["group_id"] in row["groups"]:
                    for assignment in row["assignments"]:
                        if assignment["new"]:
                            value = assignment["new"]
                            teacher_kinds.setdefault(value["teacher_id"], set()).add(value["activity"])
            active = [
                s for s in current["shares"] if s["offering_id"] == pk and s["is_active"] and s["source"] == "workload"
            ]
            expected_kinds = teacher_kinds if len(teacher_kinds) > 1 else {}
            if retained_rights.accepts(cases, current, pk, expected_kinds):
                continue
            if {s["teacher_id"]: set(s["kinds"]) for s in active} != expected_kinds:
                return False
    return True


@transaction.atomic
def run(*, organization, user, selection="", apply=False, expected_baseline="", undo=""):
    if (
        str(organization.pk) != spec.ORG
        or not organization.is_active
        or organization.status != "active"
        or not user.is_active
        or not user.is_superuser
    ):
        raise RepairError("active_tenant_superadmin_required")
    if connection.vendor != "postgresql":
        raise RepairError("postgresql_required")
    cases = state.selection(selection)
    before, impact = state.snapshot(organization, cases)
    baseline = digest(before)
    receipts = model("audit.AuditLog").objects.filter(organization=organization, resource_type=state.RESOURCE)
    if undo:
        receipt = receipts.filter(resource_id=undo).first()
        if (
            receipt is None
            or receipt.new_values.get("operation") != "apply"
            or receipt.new_values.get("selection_sha256") != digest(cases)
        ):
            raise RepairError("matching_apply_receipt_required")
        if before != receipt.new_values.get("after"):
            previous = receipts.filter(new_values__undo_of=undo).order_by("-created_at").first()
            if previous and previous.new_values.get("after") == before:
                return {
                    "baseline": baseline,
                    "status": "already_undone",
                    "applied": False,
                    "receipt": previous.resource_id,
                }
            raise RepairError("undo_state_changed")
    else:
        if desired(cases, before):
            return {"baseline": baseline, "status": "already_correct", "applied": False, "receipt": None}
        state.ensure_old(cases, before)
    result = {
        "baseline": baseline,
        "status": "dry_run",
        "applied": False,
        "receipt": None,
        "cases": list(cases),
        "impact": impact,
    }
    if not apply:
        return result
    if baseline != expected_baseline or not expected_baseline:
        raise RepairError("baseline_changed")
    batch = str(uuid.uuid4())
    if undo:
        details = receipt.new_values["details"]
        actions.undo(cases, receipt.old_values, organization=organization, user=user, batch=batch, details=details)
    else:
        details = actions.apply(cases, before, organization=organization, user=user, batch=batch)
    after, _ = state.snapshot(organization, cases)
    preserved(cases, before, after)
    if not undo and not desired(cases, after):
        raise RepairError("exact_source_state_not_reached")
    if undo:
        state.ensure_old(cases, after)
        old_assignments = {a["id"]: a for a in receipt.old_values["assignments"]}
        if {a["id"]: a for a in after["assignments"]} != old_assignments:
            raise RepairError("undo_assignment_provenance_changed")
    log_action(
        AuditAction.UPDATE,
        user=user,
        organization=organization,
        resource_type=state.RESOURCE,
        resource_id=batch,
        reason=state.RESOURCE,
        old_values=before,
        new_values={
            "operation": "undo" if undo else "apply",
            "undo_of": undo or None,
            "selection_sha256": digest(cases),
            "details": details,
            "after": after,
        },
    )
    return {
        **result,
        "status": "undone" if undo else "applied",
        "applied": True,
        "receipt": batch,
        "after_baseline": digest(after),
    }
