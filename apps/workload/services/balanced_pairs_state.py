"""Sabit 12 cütün tenant, plan/qrup və dəyişiklik sərhədləri."""

from . import balanced_pairs_spec as spec
from .sbio235_state import RepairError, digest, model, records


def manifest_sha():
    return digest(spec.SPECS)


def rows(*, lock=False):
    qs = model("workload.TeachingTaskRow").objects.filter(
        organization_id=spec.ORG,
        task_id__in={s["task_id"] for s in spec.SPECS},
        task__academic_year=spec.YEAR,
    )
    if lock:
        qs = qs.select_for_update()
    return list(qs.order_by("pk"))


def row_state(row):
    result = records(model("workload.TeachingTaskRow").objects.filter(pk=row.pk))[0]
    result["groups"] = sorted(str(pk) for pk in row.groups.values_list("pk", flat=True))
    result["assignments"] = records(row.assignments.filter(organization_id=spec.ORG))
    return result


def snapshot(tasks, all_rows):
    task_ids = [t.pk for t in tasks]
    return {
        "tasks": records(model("workload.TeachingTask").objects.filter(pk__in=task_ids, organization_id=spec.ORG)),
        "rows": [row_state(r) for r in all_rows],
        "periods": records(
            model("organizations.AcademicPeriod").objects.filter(
                organization_id=spec.ORG,
                pk__in={item["period_id"] for item in spec.SPECS},
            )
        ),
        "groups": records(
            model("organizations.OrgUnit").objects.filter(
                organization_id=spec.ORG,
                pk__in={g for item in spec.SPECS for g in item["group_ids"]},
            )
        ),
        "history": {
            name: records(model("workload." + name).objects.filter(organization_id=spec.ORG, **scope))
            for name, scope in {
                "WorkloadAmendment": {"task_id__in": task_ids},
                "TaskFacultySlice": {"task_id__in": task_ids},
                "TaskRowReview": {"row__task_id__in": task_ids},
                "LoadObjection": {"row__task_id__in": task_ids},
            }.items()
        },
    }


def validate(row, item, *, after=False):
    expected = item["after" if after else "before"]
    if str(row.task_id) != item["task_id"] or str(row.task.chair_id) != item["chair_id"]:
        raise RepairError("task_chair_mismatch")
    if row.task.status not in ("distributed", "amended"):
        raise RepairError("task_not_distributed_or_amended")
    if str(row.subject_id) != item["subject_id"] or str(row.period_id) != item["period_id"]:
        raise RepairError("subject_period_mismatch")
    if row.period.academic_year != spec.YEAR or row.season != item["season"]:
        raise RepairError("year_season_mismatch")
    if row.period.is_locked:
        raise RepairError("period_locked")
    if row.total_hours != sum(expected.values()):
        raise RepairError("row_total_mismatch")
    group_ids = sorted(str(pk) for pk in row.groups.values_list("pk", flat=True))
    if group_ids != item["group_ids"] or len(group_ids) != 1:
        raise RepairError("fixed_group_mismatch")
    group = row.groups.get()
    if not group.is_active or str(group.organization_id) != spec.ORG:
        raise RepairError("group_inactive_or_foreign")
    # Provisional single-section guard: no parent/child or az/ing equivalence is inferred.
    if row.union_count != 1 or row.subgroup_count != 1 or row.lab_plan or row.lab_total:
        raise RepairError("section_shape_requires_source_review")
    if any(getattr(row, a + "_plan") != h or getattr(row, a + "_total") != h for a, h in expected.items()):
        raise RepairError("plan_or_total_mismatch")
    if not model("auth.User").objects.filter(pk=item["teacher_id"], is_active=True).exists():
        raise RepairError("teacher_inactive")
    assignments = list(row.assignments.values_list("teacher_id", "activity", "hours"))
    if sorted(assignments) != sorted((item["teacher_id"], a, h) for a, h in expected.items()):
        raise RepairError("other_teacher_or_assignment_mismatch")
    if row.reviews.exists() or row.objections.exists():
        raise RepairError("row_history_requires_review")
    offerings = list(
        model("registrar.CourseOffering")
        .objects.select_for_update()
        .filter(
            organization_id=spec.ORG,
            subject_id=row.subject_id,
            period_id=row.period_id,
            group_id__in=group_ids,
        )
    )
    if len(offerings) != 1 or not offerings[0].is_active:
        raise RepairError("existing_single_offering_required")
    offering = offerings[0]
    if offering.instructor_id != item["teacher_id"] or offering.lesson_hours != sum(expected.values()):
        raise RepairError("journal_owner_or_plan_mismatch")
    return offerings


def protected(before, after):
    targets = {s["id"] for s in spec.SPECS}
    for old, new in zip(before["tasks"], after["tasks"]):
        for key in ("updated_at", "status"):
            old = {k: v for k, v in old.items() if k != key}
            new = {k: v for k, v in new.items() if k != key}
        if old != new:
            raise RepairError("task_metadata_changed")
    if [r for r in before["rows"] if r["id"] not in targets] != [r for r in after["rows"] if r["id"] not in targets]:
        raise RepairError("outside_workload_changed")
    if before["periods"] != after["periods"]:
        raise RepairError("period_metadata_changed")
    if before["groups"] != after["groups"]:
        raise RepairError("group_metadata_changed")
    allowed = {"updated_at", "lecture_plan", "lecture_total", "seminar_plan", "seminar_total", "assignments"}
    after_rows = {r["id"]: r for r in after["rows"]}
    for old in before["rows"]:
        if old["id"] not in targets:
            continue
        new = after_rows[old["id"]]
        if {k: v for k, v in old.items() if k not in allowed} != {k: v for k, v in new.items() if k not in allowed}:
            raise RepairError("target_metadata_changed")
        permitted = {"hours", "updated_at", "assigned_by_id"}
        if [{k: v for k, v in a.items() if k not in permitted} for a in old["assignments"]] != [
            {k: v for k, v in a.items() if k not in permitted} for a in new["assignments"]
        ]:
            raise RepairError("assignment_metadata_changed")
    for name, old in before["history"].items():
        old_ids = {v["id"] for v in old}
        new = after["history"][name]
        if [v for v in new if v["id"] in old_ids] != old:
            raise RepairError("workflow_history_changed")
        added = [v for v in new if v["id"] not in old_ids]
        if added and (name != "WorkloadAmendment" or any(str(v["target_id"]) not in targets for v in added)):
            raise RepairError("outside_workflow_changed")
