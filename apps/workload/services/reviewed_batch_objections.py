"""Receipt-backed provenance for exact named activity removals and their undo."""

from .reviewed_batch_manifest import ORG
from .reviewed_named_transitions import policy
from .sbio235_state import RepairError, model, records


def provenance(plan, before):
    """Retain the complete removed assignment and immutable objection snapshot."""
    rows = {row["id"]: row for row in before["rows"]}
    removed = {}
    for item in plan.items:
        if not policy(item):
            continue
        expected = {value["activity"] for value in item["assignments"]}
        for assignment in rows[item["row_id"]]["assignments"]:
            if assignment["activity"] in ("lecture", "seminar", "lab") and assignment["activity"] not in expected:
                removed[assignment["id"]] = assignment
    return [
        {"objection": record, "assignment": removed[record["assignment_id"]]}
        for record in before["history"]["LoadObjection"]
        if record["assignment_id"] in removed
    ]


def preserved(plan, before, after, details):
    expected = provenance(plan, before)
    if details.get("detached_objection_provenance", []) != expected:
        raise RepairError("named_objection_provenance_receipt_mismatch")
    allowed = {value["objection"]["id"]: value["objection"] for value in expected}
    current = {value["id"]: value for value in after["history"]["LoadObjection"]}
    for pk, old in allowed.items():
        if current.get(pk) != {**old, "assignment_id": None}:
            raise RepairError("named_objection_detachment_changed_history")
    return set(allowed)


def restore(plan, before):
    """Original PKs exist again; reconnect only unchanged receipt-owned history.

    Undo recreates surviving assignments too, so their objection links must also
    be reattached. All other fields, including timestamps/decisions, stay exact.
    """
    row_ids = {item["row_id"] for item in plan.items if policy(item)}
    query = model("workload.LoadObjection").objects.filter(organization_id=ORG, row_id__in=row_ids)
    saved = [value for value in before["history"]["LoadObjection"] if value["row_id"] in row_ids]
    current = {value["id"]: value for value in records(query)}
    if set(current) != {value["id"] for value in saved}:
        raise RepairError("undo_named_objection_set_changed")
    for old in saved:
        value = current[old["id"]]
        if value != old and value != {**old, "assignment_id": None}:
            raise RepairError("undo_named_objection_history_changed")
        if old["assignment_id"] is not None:
            assignment = model("workload.TeacherAssignment").objects.filter(
                organization_id=ORG, row_id=old["row_id"], pk=old["assignment_id"]
            )
            if not assignment.exists():
                raise RepairError("undo_named_objection_assignment_missing")
            query.filter(pk=old["id"]).update(assignment_id=old["assignment_id"])
    if records(query) != saved:
        raise RepairError("undo_named_objection_restore_mismatch")
