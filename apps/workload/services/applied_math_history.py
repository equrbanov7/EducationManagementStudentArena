"""One reviewed creation amendment survives duplicate retirement; every other prior event holds."""

from django.apps import apps

from .scoped_snapshot.repair_history import sha

ROW = "eb41b840-05b1-4637-8c2c-03fb8b36c0c3"
TASK = "743c143e-254a-4ef1-bf73-c368a477cc2f"
ASSIGNMENTS = ("45e4d53b-e6b0-4891-afc4-d387ee6307ec", "4db00940-f2a3-4d54-97ff-6f7730bd0af1")
PIN = {
    "id": "05d21d26-917a-40d6-8adb-16dcd01800de",
    "raw_sha256": "9c01b19d7ebd3081b196b545d9d18cbdcd15bb60bb6690c9e857d2d18a4e45f2",
    "old_sha256": "2d7cb97493f1b7f52f30db29beb3439575e853ecdfc4e621072b18214b15f7a2",
    "new_sha256": "5ba4787f304047d784cd7d4befbb48820db72dbc72475e53654d704a710755b8",
    "actor_id": 8444,
}


def query(state):
    ids = {state.REMOVE_ROW, *ASSIGNMENTS}
    ids.update(
        map(
            str,
            apps.get_model("workload.TeacherAssignment")
            .objects.filter(row_id=state.REMOVE_ROW)
            .values_list("pk", flat=True),
        )
    )
    return apps.get_model("workload.WorkloadAmendment").objects.filter(target_id__in=ids)


def capture(state):
    current = query(state)
    if current.exclude(organization_id=state.ORG).exists():
        raise state.DuplicateError("math_history_tenant_changed")
    return state.records(current)


def validate_before(state):
    rows = list(query(state).select_for_update().order_by("pk").values())
    # Isolated fixtures with different fixed identities retain the original no-history rule.
    if state.REMOVE_ROW != ROW:
        if rows:
            raise state.DuplicateError("wrong_row_has_prior_amendment")
        return
    if len(rows) != 1:
        raise state.DuplicateError("math_reviewed_creation_history_changed")
    row = rows[0]
    if (
        str(row["id"]) != PIN["id"]
        or str(row["organization_id"]) != state.ORG
        or str(row["task_id"]) != TASK
        or str(row["target_id"]) != ROW
        or row["target_kind"] != "row"
        or row["reason"] != "official"
        or row["made_by_id"] != PIN["actor_id"]
        or sha(row) != PIN["raw_sha256"]
        or sha(row["old_values"]) != PIN["old_sha256"]
        or sha(row["new_values"]) != PIN["new_sha256"]
    ):
        raise state.DuplicateError("math_reviewed_creation_history_changed")


def protected(values):
    return [r for r in values if str(r["id"]) == PIN["id"]]
