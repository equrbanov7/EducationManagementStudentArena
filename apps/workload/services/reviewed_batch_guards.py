"""Postconditions: source changes never rewrite academic content or manual access."""

from . import reviewed_batch_extensions as extensions
from .repair_fingerprints import academic_database_fingerprint
from .reviewed_batch_manifest import ACTIVITIES, ORG
from .reviewed_batch_state import offerings
from .sbio235_state import RepairError, digest, model


def protected_academic(journals, *, plan=None):
    exclude = ("offering", "handover", "journal_share") if plan and extensions.has_handovers(plan) else ("offering",)
    return academic_database_fingerprint(organization_id=ORG, offerings=journals, exclude=exclude)


def manual_shares(journals, *, plan=None):
    from .reviewed_batch_state import db_fingerprint

    query = (
        model("registrar.JournalShare")
        .objects.filter(organization_id=ORG, offering_id__in=[o.pk for o in journals])
        .exclude(source="workload")
    )
    if plan:
        from django.db.models import Q

        excluded = Q(pk__in=[])
        for item in plan.items:
            value = extensions.policy(item, "handover")
            if value:
                excluded |= Q(
                    offering_id__in=value["offering_ids"],
                    teacher_id__in=[value["from_instructor_id"], value["to_instructor_id"]],
                )
        query = query.exclude(excluded)
    return db_fingerprint(query)


def _same_except(old, new, allowed, code):
    if {key: value for key, value in old.items() if key not in allowed} != {
        key: value for key, value in new.items() if key not in allowed
    }:
        raise RepairError(code)


def preserved(plan, before, after, details):
    extensions.preserved(plan, before, after, details)
    for name in ("roles", "teachers", "profiles", "periods", "programs"):
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
        handover_item = next(
            (i for i in plan.items if i["row_id"] == old["id"] and extensions.policy(i, "handover")), None
        )
        assignments = {value["id"]: value for value in new["assignments"]}
        for assignment in old["assignments"]:
            if assignment["id"] not in assignments:
                if handover_item and assignment["activity"] not in {
                    a["activity"] for a in handover_item["assignments"]
                }:
                    continue
                raise RepairError("existing_assignment_deleted")
            _same_except(
                assignment,
                assignments[assignment["id"]],
                {"hours", "assigned_by_id", "updated_at", "is_hourly_paid"}
                | ({"teacher_id"} if handover_item else set()),
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
        owners = extensions.handover_targets(plan)
        _same_except(
            old,
            current[pk],
            {"lesson_hours", "updated_at"} | ({"instructor_id"} if pk in owners else set()),
            "existing_journal_owner_or_identity_changed",
        )
        if pk in owners and current[pk]["instructor_id"] != owners[pk]:
            raise RepairError("unreviewed_handover_target")
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
                or journal.lesson_hours != extensions.journal_hours(item, journal.pk)
            ):
                raise RepairError("after_journal_owner_hours_or_presence_mismatch")
