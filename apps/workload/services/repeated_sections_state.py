"""Təkrar bölmə düzəlişinin tenant, kimlik, vahid saat və qoruma sərhədləri."""

from . import repeated_sections_spec as spec
from .sbio235_state import RepairError, digest, model, records


class BatchState:
    def __init__(self, items):
        self.items = items

    def manifest_sha(self):
        return digest(self.items)

    def rows(self, *, lock=False):
        qs = model("workload.TeachingTaskRow").objects.filter(
            organization_id=spec.ORG,
            task_id__in={s["task_id"] for s in self.items},
            task__academic_year=spec.YEAR,
        )
        if lock:
            qs = qs.select_for_update()
        return list(qs.order_by("pk"))

    def row_state(self, row):
        result = records(model("workload.TeachingTaskRow").objects.filter(pk=row.pk))[0]
        result["groups"] = sorted(str(pk) for pk in row.groups.values_list("pk", flat=True))
        result["assignments"] = records(row.assignments.filter(organization_id=spec.ORG))
        return result

    def snapshot(self, tasks, all_rows):
        task_ids = [t.pk for t in tasks]
        return {
            "tasks": records(model("workload.TeachingTask").objects.filter(pk__in=task_ids, organization_id=spec.ORG)),
            "rows": [self.row_state(r) for r in all_rows],
            "periods": records(
                model("organizations.AcademicPeriod").objects.filter(
                    organization_id=spec.ORG,
                    pk__in={item["period_id"] for item in self.items},
                )
            ),
            "groups": records(
                model("organizations.OrgUnit").objects.filter(
                    organization_id=spec.ORG,
                    pk__in={g for item in self.items for g in item["group_ids"]},
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

    def validate(self, row, item, *, after=False):
        count = item["after_count" if after else "before_count"]
        unit = item["unit_hours"]
        if str(row.organization_id) != spec.ORG or str(row.task.organization_id) != spec.ORG:
            raise RepairError("foreign_row_or_task")
        if str(row.task_id) != item["task_id"] or str(row.task.chair_id) != item["chair_id"]:
            raise RepairError("task_chair_mismatch")
        if row.task.status not in ("distributed", "amended"):
            raise RepairError("task_not_distributed_or_amended")
        if str(row.subject_id) != item["subject_id"] or str(row.period_id) != item["period_id"]:
            raise RepairError("subject_period_mismatch")
        if str(row.subject.organization_id) != spec.ORG or str(row.period.organization_id) != spec.ORG:
            raise RepairError("foreign_subject_or_period")
        if row.period.academic_year != spec.YEAR or row.season != item["season"]:
            raise RepairError("year_season_mismatch")
        if row.period.is_locked:
            raise RepairError("period_locked")
        groups = list(row.groups.order_by("pk"))
        if [str(g.pk) for g in groups] != item["group_ids"]:
            raise RepairError("fixed_group_mismatch")
        if any(not g.is_active or str(g.organization_id) != spec.ORG or g.unit_type != "group" for g in groups):
            raise RepairError("group_inactive_or_foreign")
        if row.union_count != 1 or row.subgroup_count != count or row.lab_plan or row.lab_total:
            raise RepairError("section_shape_mismatch")
        if (row.lecture_plan, row.lecture_total, row.seminar_plan, row.seminar_total, row.total_hours) != (
            unit,
            unit,
            unit,
            unit * count,
            unit * (1 + count),
        ):
            raise RepairError("unit_or_total_mismatch")
        if not model("auth.User").objects.filter(pk=item["teacher_id"], is_active=True).exists():
            raise RepairError("teacher_inactive")
        assignments = list(row.assignments.all())
        expected = sorted(
            (item["assignment_ids"][a], item["teacher_id"], a, unit * (count if a == "seminar" else 1))
            for a in ("lecture", "seminar")
        )
        actual = sorted((str(a.pk), a.teacher_id, a.activity, a.hours) for a in assignments)
        if actual != expected or any(str(a.organization_id) != spec.ORG for a in assignments):
            raise RepairError("assignment_identity_or_hours_mismatch")
        if row.reviews.exists() or row.objections.exists():
            raise RepairError("row_history_requires_review")
        offerings = list(
            model("registrar.CourseOffering")
            .objects.select_for_update()
            .filter(
                organization_id=spec.ORG,
                subject_id=row.subject_id,
                period_id=row.period_id,
                group_id__in=item["group_ids"],
            )
            .order_by("pk")
        )
        if [str(o.pk) for o in offerings] != item["offering_ids"] or len(offerings) != len(groups):
            raise RepairError("fixed_offering_identity_mismatch")
        if any(str(o.group_id) != item["offering_groups"][str(o.pk)] for o in offerings):
            raise RepairError("fixed_offering_group_mismatch")
        if any(
            not o.is_active or o.instructor_id != item["teacher_id"] or o.lesson_hours != unit * 2 for o in offerings
        ):
            raise RepairError("journal_owner_or_unit_plan_mismatch")
        return offerings

    def protected(self, before, after):
        targets = {s["id"] for s in self.items}
        for old, new in zip(before["tasks"], after["tasks"]):
            for key in ("updated_at", "status"):
                old = {k: v for k, v in old.items() if k != key}
                new = {k: v for k, v in new.items() if k != key}
            if old != new:
                raise RepairError("task_metadata_changed")
        if [r for r in before["rows"] if r["id"] not in targets] != [
            r for r in after["rows"] if r["id"] not in targets
        ]:
            raise RepairError("outside_workload_changed")
        if before["periods"] != after["periods"]:
            raise RepairError("period_metadata_changed")
        if before["groups"] != after["groups"]:
            raise RepairError("group_metadata_changed")
        allowed = {"updated_at", "subgroup_count", "seminar_total", "total_hours", "assignments"}
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
