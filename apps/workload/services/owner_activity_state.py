"""Sabit allowlist seçimi və tam tenant-scoped workload/jurnal sərhədləri."""

import uuid
from collections import defaultdict

from . import owner_activity_spec as spec
from .sbio235_state import RepairError, digest, model, records

ACTIVITIES = ("lecture", "seminar", "lab")


def manifest_sha():
    return digest(spec.SPECS)


def select(*, row_ids=(), chair_ids=()):
    if bool(row_ids) == bool(chair_ids):
        raise RepairError("exactly_one_explicit_selection_required")
    raw = row_ids or chair_ids
    try:
        normalized = [str(uuid.UUID(str(v).strip())) for v in raw]
    except (ValueError, TypeError, AttributeError) as exc:
        raise RepairError("selection_uuid_invalid") from exc
    if len(set(normalized)) != len(normalized):
        raise RepairError("duplicate_selection")
    key = "id" if row_ids else "chair_id"
    allowed = {s[key] for s in spec.SPECS}
    if not normalized or not set(normalized) <= allowed:
        raise RepairError("selection_outside_fixed_allowlist")
    return Scope(tuple(sorted((s for s in spec.SPECS if s[key] in normalized), key=lambda s: s["id"])))


def workload_records(qs, *, lock=False):
    data = records(qs, lock=lock)
    row_ids = [r["id"] for r in data]
    assignments, groups = defaultdict(list), defaultdict(list)
    for assignment in records(
        model("workload.TeacherAssignment").objects.filter(
            organization_id=spec.ORG,
            row_id__in=row_ids,
        ),
        lock=lock,
    ):
        assignments[assignment["row_id"]].append(assignment)
    through = model("workload.TeachingTaskRow").groups.through
    for row_id, group_id in through.objects.filter(teachingtaskrow_id__in=row_ids).values_list(
        "teachingtaskrow_id",
        "orgunit_id",
    ):
        groups[str(row_id)].append(str(group_id))
    for row in data:
        row["groups"] = sorted(groups[row["id"]])
        row["assignments"] = assignments[row["id"]]
    return data


class Scope:
    def __init__(self, items):
        self.items = items
        self.row_ids = {s["id"] for s in items}
        self.task_ids = {s["task_id"] for s in items}
        self.group_ids = {g for s in items for g in s["group_ids"]}
        self.period_ids = {s["period_id"] for s in items}
        self.teacher_ids = {s["teacher_id"] for s in items}
        self.selection_sha = digest({"source": manifest_sha(), "rows": sorted(self.row_ids)})

    def rows(self):
        return model("workload.TeachingTaskRow").objects.filter(
            organization_id=spec.ORG,
            task_id__in=self.task_ids,
            task__academic_year=spec.YEAR,
        )

    def snapshot(self, *, lock=False):
        return {
            "selection": self.selection_sha,
            "tasks": records(
                model("workload.TeachingTask").objects.filter(
                    organization_id=spec.ORG,
                    academic_year=spec.YEAR,
                    pk__in=self.task_ids,
                ),
                lock=lock,
            ),
            "rows": workload_records(self.rows(), lock=lock),
            "groups": records(
                model("organizations.OrgUnit").objects.filter(
                    organization_id=spec.ORG,
                    pk__in=self.group_ids,
                ),
                lock=lock,
            ),
            "periods": records(
                model("organizations.AcademicPeriod").objects.filter(
                    organization_id=spec.ORG,
                    pk__in=self.period_ids,
                ),
                lock=lock,
            ),
            "history": {
                name: records(
                    model("workload." + name).objects.filter(
                        organization_id=spec.ORG,
                        **where,
                    )
                )
                for name, where in {
                    "WorkloadAmendment": {"task_id__in": self.task_ids},
                    "TaskFacultySlice": {"task_id__in": self.task_ids},
                    "TaskRowReview": {"row__task_id__in": self.task_ids},
                    "LoadObjection": {"row__task_id__in": self.task_ids},
                }.items()
            },
        }

    def baseline(self, snapshot):
        return digest({"selection": self.selection_sha, "state": snapshot})

    def outside(self, offerings):
        return digest(
            {
                "rows": workload_records(
                    model("workload.TeachingTaskRow")
                    .objects.filter(
                        organization_id=spec.ORG,
                        task__academic_year=spec.YEAR,
                    )
                    .exclude(task_id__in=self.task_ids)
                ),
                "tasks": records(
                    model("workload.TeachingTask")
                    .objects.filter(
                        organization_id=spec.ORG,
                        academic_year=spec.YEAR,
                    )
                    .exclude(pk__in=self.task_ids)
                ),
                "offerings": records(
                    model("registrar.CourseOffering")
                    .objects.filter(
                        organization_id=spec.ORG,
                        period__academic_year=spec.YEAR,
                    )
                    .exclude(pk__in=[o.pk for o in offerings])
                ),
                "roles": records(
                    model("organizations.Role").objects.filter(
                        organization_id=spec.ORG,
                        pk__in=model("organizations.Membership")
                        .objects.filter(
                            organization_id=spec.ORG,
                            user_id__in=self.teacher_ids,
                        )
                        .values("role_id"),
                    )
                ),
                "outside_shares": records(
                    model("registrar.JournalShare")
                    .objects.filter(
                        organization_id=spec.ORG,
                        offering__period__academic_year=spec.YEAR,
                    )
                    .exclude(offering_id__in=[o.pk for o in offerings])
                ),
                "access": records(
                    model("organizations.Membership").objects.filter(
                        organization_id=spec.ORG,
                        user_id__in=self.teacher_ids,
                    )
                ),
            }
        )

    def validate(self, row, item, *, after=False):
        expected = item["after" if after else "before"]
        if str(row.task_id) != item["task_id"] or str(row.task.chair_id) != item["chair_id"]:
            raise RepairError("task_chair_mismatch")
        if row.task.status not in ("distributed", "amended") or row.task.academic_year != spec.YEAR:
            raise RepairError("task_stage_or_year_mismatch")
        if str(row.subject_id) != item["subject_id"] or str(row.period_id) != item["period_id"]:
            raise RepairError("subject_period_mismatch")
        if row.season != item["season"] or row.period.academic_year != spec.YEAR or row.period.is_locked:
            raise RepairError("period_season_or_lock_mismatch")
        groups = list(row.groups.all())
        if sorted(str(g.pk) for g in groups) != item["group_ids"] or len(groups) != 1:
            raise RepairError("fixed_physical_group_mismatch")
        if not groups[0].is_active or str(groups[0].organization_id) != spec.ORG:
            raise RepairError("group_inactive_or_foreign")
        if row.union_count != 1 or row.subgroup_count != 1:
            raise RepairError("section_shape_requires_fresh_review")
        if row.total_hours != sum(expected.values()) or sum(item["before"].values()) != sum(item["after"].values()):
            raise RepairError("total_hours_mismatch")
        if any(getattr(row, a + suffix) != expected.get(a, 0) for a in ACTIVITIES for suffix in ("_plan", "_total")):
            raise RepairError("plan_or_unit_hours_mismatch")
        assignments = list(row.assignments.all())
        if sorted((a.teacher_id, a.activity, a.hours) for a in assignments) != sorted(
            (item["teacher_id"], a, h) for a, h in expected.items()
        ):
            raise RepairError("teacher_or_activity_assignment_mismatch")
        if len({a.is_hourly_paid for a in assignments}) != 1:
            raise RepairError("payment_flag_mismatch")
        if not model("auth.User").objects.filter(pk=item["teacher_id"], is_active=True).exists():
            raise RepairError("teacher_inactive")
        from ..public import is_assignable_teacher

        teacher = model("auth.User").objects.get(pk=item["teacher_id"])
        if not is_assignable_teacher(row.organization, row.task.chair, teacher):
            raise RepairError("existing_chair_membership_required")
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
        )
        if len(offerings) != 1 or not offerings[0].is_active:
            raise RepairError("existing_single_journal_required")
        if offerings[0].instructor_id != item["teacher_id"] or offerings[0].lesson_hours != row.total_hours:
            raise RepairError("existing_owner_or_journal_plan_mismatch")
        return offerings

    def protected(self, before, after, *, created_ids, undo=False):
        if before["groups"] != after["groups"] or before["periods"] != after["periods"]:
            raise RepairError("group_or_period_metadata_changed")
        for old, new in zip(before["tasks"], after["tasks"]):
            if new["status"] != "amended" or {k: v for k, v in old.items() if k not in ("status", "updated_at")} != {
                k: v for k, v in new.items() if k not in ("status", "updated_at")
            }:
                raise RepairError("task_metadata_changed")
        after_rows = {r["id"]: r for r in after["rows"]}
        if {r["id"] for r in before["rows"]} != set(after_rows):
            raise RepairError("workload_row_set_changed")
        allowed = {"updated_at", "assignments"} | {a + suffix for a in ACTIVITIES for suffix in ("_plan", "_total")}
        for old in before["rows"]:
            new = after_rows[old["id"]]
            if old["id"] not in self.row_ids:
                if old != new:
                    raise RepairError("outside_row_changed")
                continue
            if {k: v for k, v in old.items() if k not in allowed} != {k: v for k, v in new.items() if k not in allowed}:
                raise RepairError("target_metadata_changed")
            old_assign = {a["id"]: a for a in old["assignments"]}
            new_assign = {a["id"]: a for a in new["assignments"]}
            removed, added = set(old_assign) - set(new_assign), set(new_assign) - set(old_assign)
            permitted = created_ids.get(old["id"], set())
            if (removed, added) != ((permitted, set()) if undo else (set(), permitted)):
                raise RepairError("assignment_identity_changed")
            for pk in set(old_assign) & set(new_assign):
                ignore = {"hours", "updated_at", "assigned_by_id"}
                if {k: v for k, v in old_assign[pk].items() if k not in ignore} != {
                    k: v for k, v in new_assign[pk].items() if k not in ignore
                }:
                    raise RepairError("assignment_metadata_changed")
        for name, old in before["history"].items():
            ids = {r["id"] for r in old}
            new = after["history"][name]
            if [r for r in new if r["id"] in ids] != old:
                raise RepairError("workflow_history_changed")
            added = [r for r in new if r["id"] not in ids]
            if added and (name != "WorkloadAmendment" or any(str(r["target_id"]) not in self.row_ids for r in added)):
                raise RepairError("outside_workflow_changed")
