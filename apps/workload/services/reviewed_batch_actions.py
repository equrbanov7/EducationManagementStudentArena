"""Canonical, bounded writes for a reviewed source selection."""

from collections import defaultdict

from django.db.models import Max

from core.audit import log_action
from core.constants import AuditAction

from ..constants import AmendmentReason
from . import reviewed_batch_electives as electives
from . import reviewed_batch_extensions as extensions
from .assignments import assign_teacher, unassign
from .offering_sync import sync_task_offerings
from .reviewed_batch_manifest import ACTIVITIES, FORMS, ORG
from .row_edit import delete_row_amended, save_row_amended
from .sbio235_state import RepairError, model


def amendment(batch):
    return {"reason": AmendmentReason.CORRECTION, "note": f"Rəsmi kafedra mənbəsi üzrə baxılmış dəst [batch:{batch}]"}


def assign(row, value, *, actor, old=None):
    return assign_teacher(
        row=row,
        actor=actor,
        assignment=old,
        activity=value["activity"],
        teacher_id=value["teacher_id"],
        hours=value["hours"],
        is_hourly_paid=value["is_hourly_paid"],
        groups_note=old.groups_note if old else "",
        note=old.note if old else "Rəsmi baxılmış mənbə sətri",
        sync_offerings=False,
    )


def _row_data(item):
    from .reviewed_batch_state import row_degree_level

    value = item["row_data"]
    data = {
        "subject_id": item["subject_id"],
        "period_id": item["period_id"],
        "group_ids": item["group_ids"],
        "groups_text": value["groups_text"],
        "subject_text": item["subject"]["name"],
        "specialty_id": value.get("specialty_id"),
        "season": item["season"],
        "row_kind": "teaching",
        "degree_level": row_degree_level(item),
        "education_form": FORMS[value["education_form"]],
        "credits": "" if value.get("credits") is None else str(value["credits"]),
        "student_count_text": "" if value.get("student_count") is None else str(value["student_count"]),
        "union_count": item["union_count"],
        "subgroup_count": item["subgroup_count"],
        **{kind + "_plan": item["plan"][kind] for kind in ACTIVITIES},
        **{kind + "_total": item["totals"][kind] for kind in ACTIVITIES},
    }
    raw_credits = value.get("credits")
    credit_text = "" if raw_credits is None else str(raw_credits).strip()
    if not isinstance(raw_credits, bool) and credit_text.isdigit() and 0 <= int(credit_text) <= 60:
        data["credits_value"] = int(credit_text)
    raw_count = value.get("student_count")
    if isinstance(raw_count, int) and not isinstance(raw_count, bool) and raw_count >= 0:
        data["student_count"] = raw_count
    elif isinstance(raw_count, str) and raw_count.strip().isdigit():
        data["student_count"] = int(raw_count.strip())
    return data


def edit(row, item, *, actor, batch):
    # Open the normal row amendment without interim sync before reducing any
    # assignment; save_row still enforces totals >= already assigned hours.
    row = save_row_amended(task=row.task, actor=actor, row=row, data={}, amend=amendment(batch), sync_offerings=False)
    if extensions.policy(item, "handover"):
        _handover_assignments(row, item, actor=actor)
    current = {(a.teacher_id, a.activity): a for a in row.assignments.filter(activity__in=ACTIVITIES)}
    expected = {(a["teacher_id"], a["activity"]): a for a in item["assignments"]}
    if set(current) - set(expected):
        raise RepairError("unexpected_assignment_owner_or_activity")
    for key, old in current.items():
        desired = expected[key]
        if desired["hours"] < old.hours:
            current[key] = assign(row, desired, actor=actor, old=old)
    data = {
        **{kind + "_plan": item["plan"][kind] for kind in ACTIVITIES},
        **{kind + "_total": item["totals"][kind] for kind in ACTIVITIES},
        "union_count": item["union_count"],
        "subgroup_count": item["subgroup_count"],
    }
    if "manual_total_hours" in item:
        data["total_hours"] = item["manual_total_hours"]
    row = save_row_amended(task=row.task, actor=actor, row=row, data=data, amend=amendment(batch), sync_offerings=False)
    for key, desired in expected.items():
        old = current.get(key)
        if old is None or (old.hours, old.is_hourly_paid) != (desired["hours"], desired["is_hourly_paid"]):
            assign(row, desired, actor=actor, old=old)
    return row


def _handover_assignments(row, item, *, actor):
    """Keep surviving contribution IDs, audit superseded activity removal."""
    value = extensions.policy(item, "handover")
    expected = {a["activity"]: a for a in item["assignments"]}
    for old in list(row.assignments.filter(activity__in=ACTIVITIES)):
        if old.teacher_id != value["from_instructor_id"]:
            raise RepairError("reviewed_handover_assignment_teacher_changed")
        desired = expected.get(old.activity)
        if desired is None:
            unassign(assignment=old, actor=actor, sync_offerings=False)
        else:
            assign(row, {**desired, "hours": min(desired["hours"], old.hours)}, actor=actor, old=old)


def apply_metadata(plan, *, user, batch):
    changed = []
    for fix in plan.metadata_fixes:
        group = model("organizations.OrgUnit").objects.get(organization_id=ORG, pk=fix["group_id"])
        if group.name != fix["group_name"]:
            raise RepairError("reviewed_english_group_name_changed")
        before = dict(group.settings or {})
        if all(before.get(key) == value for key, value in fix["new_values"].items()):
            continue
        for key, value in fix["old_known_settings"].items():
            if before.get(key) != value:
                raise RepairError("reviewed_english_group_metadata_changed")
        group.settings = {**before, **fix["new_values"]}
        group.save(update_fields=["settings", "updated_at"])
        log_action(
            AuditAction.UPDATE,
            user=user,
            organization=group.organization,
            obj=group,
            reason=f"workload.reviewed_source_english_sector [batch:{batch}]",
            old_values={"settings": before},
            new_values={"settings": group.settings},
        )
        changed.append(str(group.pk))
    return changed


def forward(plan, *, tasks, rows, actor, user, batch):
    result = {
        "created_row_ids": [],
        "changed_row_ids": [],
        "metadata_group_ids": apply_metadata(plan, user=user, batch=batch),
    }
    selected = []
    for item in plan.items:
        row = rows.get(item["line"])
        if row is None:
            task = tasks[item["task_id"]]
            data = _row_data(item)
            data["order"] = (task.rows.aggregate(value=Max("order"))["value"] or 0) + 1
            row = save_row_amended(task=task, actor=actor, data=data, amend=amendment(batch), sync_offerings=False)
            for assignment in item["assignments"]:
                assign(row, assignment, actor=actor)
            result["created_row_ids"].append(str(row.pk))
        else:
            row = edit(row, item, actor=actor, batch=batch)
            result["changed_row_ids"].append(str(row.pk))
        row.refresh_from_db()
        row.task = tasks[item["task_id"]]
        selected.append(row)
    sync(plan, tasks=tasks, rows=selected, actor=actor)
    extensions.retain_capacities(plan)
    return result


def sync(plan, *, tasks, rows, actor):
    # Only exact keys of create-mode items may create journals. Restore/patch
    # rows use create=False, so no workload import or task-wide confirm runs.
    allowed = {item["task_id"]: set() for item in plan.items}
    for item in plan.items:
        if item["mode"] == "create":
            allowed[item["task_id"]].add((item["subject_id"], item["period_id"], tuple(item["group_ids"])))
    grouped = defaultdict(list)
    for row in rows:
        grouped[str(row.task_id)].append(row)
    for task_id, selected in grouped.items():
        new, existing = [], []
        for row in selected:
            key = (
                str(row.subject_id),
                str(row.period_id),
                tuple(sorted(map(str, row.groups.values_list("pk", flat=True)))),
            )
            (new if key in allowed[task_id] else existing).append(row)
        for subset, create in ((existing, False), (new, True)):
            if not subset:
                continue
            report = sync_task_offerings(
                tasks[task_id],
                actor=actor,
                rows=subset,
                create=create,
                _reviewed_choices=electives.for_rows(plan, subset) if create else None,
            )
            blocked = (
                "blocked",
                "inactive_skipped",
                "elective_pending",
                "elective_choice_failed",
                "elective_choice_conflict",
                "period_locked",
            )
            if any(report.get(key) for key in blocked):
                raise RepairError("bounded_sync_rejected_source_course")
            if not create and report.get("created"):
                raise RepairError("existing_course_created_an_extra_journal")


def undo_rows(plan, *, before, details, actor, batch):
    saved = {row["id"]: row for row in before["rows"]}
    for rid in details["created_row_ids"]:
        row = model("workload.TeachingTaskRow").objects.select_related("task").get(pk=rid, organization_id=ORG)
        for assignment in list(row.assignments.all()):
            unassign(assignment=assignment, actor=actor, sync_offerings=False)
        delete_row_amended(task=row.task, row=row, actor=actor, amend=amendment(batch))
    for rid in details["changed_row_ids"]:
        row = model("workload.TeachingTaskRow").objects.select_related("task").get(pk=rid, organization_id=ORG)
        old = saved[rid]
        current = {str(a.pk): a for a in row.assignments.all()}
        old_ids = {a["id"] for a in old["assignments"]}
        for pk, assignment in current.items():
            if pk not in old_ids:
                unassign(assignment=assignment, actor=actor, sync_offerings=False)
        if any(i["row_id"] == rid and extensions.policy(i, "handover") for i in plan.items):
            for assignment in list(row.assignments.filter(activity__in=ACTIVITIES)):
                unassign(assignment=assignment, actor=actor, sync_offerings=False)
            row = save_row_amended(
                task=row.task,
                actor=actor,
                row=row,
                data={kind + suffix: old[kind + suffix] for kind in ACTIVITIES for suffix in ("_plan", "_total")},
                amend=amendment(batch),
                sync_offerings=False,
            )
            for saved_assignment in old["assignments"]:
                if saved_assignment["activity"] not in ACTIVITIES:
                    continue
                restored = model("workload.TeacherAssignment")(
                    pk=saved_assignment["id"],
                    row=row,
                    organization_id=ORG,
                    groups_note=saved_assignment["groups_note"],
                    note=saved_assignment["note"],
                )
                assign(row, saved_assignment, actor=actor, old=restored)
        item = {
            "assignments": [
                {k: a[k] for k in ("teacher_id", "activity", "hours", "is_hourly_paid")}
                for a in old["assignments"]
                if a["activity"] in ACTIVITIES
            ],
            "plan": {kind: old[kind + "_plan"] for kind in ACTIVITIES},
            "totals": {kind: old[kind + "_total"] for kind in ACTIVITIES},
            "manual_total_hours": old["total_hours"],
            "union_count": old["union_count"],
            "subgroup_count": old["subgroup_count"],
        }
        edit(row, item, actor=actor, batch=batch)
    for saved_group in before["groups"]:
        if saved_group["id"] in details["metadata_group_ids"]:
            group = model("organizations.OrgUnit").objects.get(pk=saved_group["id"], organization_id=ORG)
            group.settings = saved_group["settings"]
            group.save(update_fields=["settings", "updated_at"])
