"""Postconditions: source changes never rewrite academic content or manual access."""

from .repair_fingerprints import academic_database_fingerprint
from .reviewed_batch_manifest import ACTIVITIES, ORG
from .reviewed_batch_state import offerings
from .sbio235_state import RepairError, digest, model


def protected_academic(journals):
    return academic_database_fingerprint(organization_id=ORG, offerings=journals, exclude=("offering",))


def manual_shares(journals):
    from .reviewed_batch_state import db_fingerprint

    return db_fingerprint(
        model("registrar.JournalShare")
        .objects.filter(organization_id=ORG, offering_id__in=[o.pk for o in journals])
        .exclude(source="workload")
    )


def _same_except(old, new, allowed, code):
    if {key: value for key, value in old.items() if key not in allowed} != {
        key: value for key, value in new.items() if key not in allowed
    }:
        raise RepairError(code)


def preserved(plan, before, after, details):
    for name in ("memberships", "roles", "teachers", "profiles", "subjects", "periods", "programs"):
        if digest(before[name]) != digest(after[name]):
            raise RepairError(name + "_changed")
    groups = {row["id"]: row for row in after["groups"]}
    for old in before["groups"]:
        allowed = {"updated_at", "settings"} if old["id"] in details["metadata_group_ids"] else set()
        new = groups[old["id"]]
        _same_except(old, new, allowed, "group_identity_or_scope_changed")
        if allowed:
            _same_except(
                old["settings"], new["settings"], {"sector", "language_sector"}, "unrelated_group_setting_changed"
            )
    tasks = {row["id"]: row for row in after["tasks"]}
    for old in before["tasks"]:
        _same_except(old, tasks[old["id"]], {"status", "updated_at"}, "task_history_or_scope_changed")
    changed = set(details["changed_row_ids"])
    rows = {row["id"]: row for row in after["rows"]}
    fields = {kind + suffix for kind in ACTIVITIES for suffix in ("_plan", "_total")}
    fields |= {"total_hours", "union_count", "subgroup_count", "updated_at", "assignments"}
    for old in before["rows"]:
        new = rows.get(old["id"])
        if new is None:
            raise RepairError("existing_row_deleted")
        if old["id"] not in changed:
            if old != new:
                raise RepairError("unselected_workload_row_changed")
            continue
        _same_except(old, new, fields, "existing_row_reference_or_noncontact_changed")
        assignments = {value["id"]: value for value in new["assignments"]}
        for assignment in old["assignments"]:
            if assignment["id"] not in assignments:
                raise RepairError("existing_assignment_deleted")
            _same_except(
                assignment,
                assignments[assignment["id"]],
                {"hours", "assigned_by_id", "updated_at"},
                "existing_assignment_identity_or_note_changed",
            )
    for name, previous in before["history"].items():
        current_history = {record["id"]: record for record in after["history"][name]}
        for record in previous:
            if record != current_history.get(record["id"]):
                raise RepairError("existing_workload_history_changed")
        if name != "WorkloadAmendment" and len(current_history) != len(previous):
            raise RepairError("unreviewed_workload_history_created")
    old_offerings = {value["id"]: value for value in before["offerings"]}
    current = {value["id"]: value for value in after["offerings"]}
    for pk, old in old_offerings.items():
        if pk not in current:
            raise RepairError("existing_journal_deleted")
        _same_except(old, current[pk], {"lesson_hours", "updated_at"}, "existing_journal_owner_or_identity_changed")
    allowed_new = {
        (item["subject_id"], item["period_id"], group)
        for item in plan.items
        if item["mode"] == "create"
        for group in item["group_ids"]
    }
    for pk, value in current.items():
        if pk not in old_offerings and (value["subject_id"], value["period_id"], value["group_id"]) not in allowed_new:
            raise RepairError("new_journal_outside_explicit_source_keys")


def verify_after(plan):
    journals = {(str(o.subject_id), str(o.period_id), str(o.group_id)): o for o in offerings(plan)}
    for item in plan.items:
        rows = (
            model("workload.TeachingTaskRow")
            .objects.filter(
                organization_id=ORG,
                task_id=item["task_id"],
                subject_id=item["subject_id"],
                period_id=item["period_id"],
                groups__pk__in=item["group_ids"],
            )
            .distinct()
        )
        if rows.count() != 1:
            raise RepairError("after_source_course_not_one_logical_row")
        row = rows.get()
        if sorted(map(str, row.groups.values_list("pk", flat=True))) != item["group_ids"]:
            raise RepairError("after_source_group_set_mismatch")
        if any(
            getattr(row, kind + "_plan") != item["plan"][kind] or getattr(row, kind + "_total") != item["totals"][kind]
            for kind in ACTIVITIES
        ):
            raise RepairError("after_source_hours_mismatch")
        got = sorted(
            (a.teacher_id, a.activity, a.hours, a.is_hourly_paid)
            for a in row.assignments.filter(activity__in=ACTIVITIES)
        )
        want = sorted((a["teacher_id"], a["activity"], a["hours"], a["is_hourly_paid"]) for a in item["assignments"])
        if got != want:
            raise RepairError("after_source_contribution_mismatch")
        for gid in item["group_ids"]:
            journal = journals.get((item["subject_id"], item["period_id"], gid))
            if (
                journal is None
                or not journal.is_active
                or journal.instructor_id != item["assignments"][0]["teacher_id"]
                or journal.lesson_hours != item["contacts"]
            ):
                raise RepairError("after_journal_owner_hours_or_presence_mismatch")
