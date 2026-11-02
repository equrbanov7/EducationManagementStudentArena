"""Lock the full three-journal closure; normalize only reviewed contact metadata."""

import copy

from django.db import connection

from apps.registrar.public import schedule_lock

from . import reviewed_history636_spec as spec
from . import reviewed_two_catalog_schema as schema
from .group_projection import project_group_settings
from .people import is_assignable_teacher
from .reviewed_leyla_catalog_graph import bounded, digest, graph, model, require
from .scoping import ensure_can_distribute, resolve_actor


def same(value, pin):
    return all(value.get(k) == v for k, v in pin.items())


def row_after(row):
    return {
        **row,
        "lecture_plan": 0,
        "lecture_total": 0,
        "seminar_plan": 30,
        "seminar_total": 30,
        "total_hours": 30,
        "union_count": 0,
    }


def snapshot(org, actor):
    p = spec.PINS
    require(connection.vendor == "postgresql", "history636_postgresql_required")
    require(schema.fingerprints() == spec.SCHEMA, "history636_schema_changed")
    schedule_lock.lock_schedule(spec.ORG, spec.PERIOD)
    periods = bounded(model("organizations.AcademicPeriod").objects.filter(organization=org, pk=spec.PERIOD), cap=1)
    require(
        len(periods) == 1
        and periods[0]["is_active"]
        and periods[0]["locked_at"] is None
        and periods[0]["academic_year"] == p["year"],
        "history636_period_changed",
    )
    task_ids = {r["task_id"] for r in p["rows"].values()}
    tasks = bounded(model("workload.TeachingTask").objects.filter(organization=org, pk__in=task_ids), cap=2)
    require(
        {t["id"] for t in tasks} == task_ids
        and all(
            t["status"] == "amended" and t["academic_year"] == p["year"] and t["chair_id"] == p["task_chairs"][t["id"]]
            for t in tasks
        ),
        "history636_tasks_changed",
    )
    allocation_actor = resolve_actor(actor, org)
    for task in tasks:
        ensure_can_distribute(allocation_actor, task["chair_id"])
    users = bounded(model("auth.User").objects.filter(pk__in=[p["teacher"], p["other_teacher"]]), cap=2)
    require(
        {str(u["id"]): u["username"] for u in users} == p["usernames"] and all(u["is_active"] for u in users),
        "history636_teacher_identity_changed",
    )
    other_row = next(a["row_id"] for a in p["assignments"].values() if a["teacher_id"] == p["other_teacher"])
    # Check only the destination of the NEW lecture allocation. The old foreign
    # lecture is removed, not recreated or used to grant another membership.
    for teacher_id, task_id in ((p["teacher"], p["task"]), (p["other_teacher"], p["rows"][other_row]["task_id"])):
        task = model("workload.TeachingTask").objects.select_related("chair").get(pk=task_id)
        teacher = model("auth.User").objects.get(pk=teacher_id)
        require(is_assignable_teacher(org, task.chair, teacher), "history636_teacher_scope_changed")
    groups = bounded(model("organizations.OrgUnit").objects.filter(organization=org, pk__in=p["groups"]), cap=3)
    require(
        {g["id"] for g in groups} == set(p["groups"])
        and all(
            same(
                {**g, "settings": project_group_settings(g["settings"], canonical_group_ids=p["groups"])},
                p["group_pins"][g["id"]],
            )
            for g in groups
        ),
        "history636_group_identity_changed",
    )
    rows = bounded(
        model("workload.TeachingTaskRow").objects.filter(organization=org, pk__in=[*p["rows"], p["new_row"]]), cap=4
    )
    corrected = any(r["id"] == p["new_row"] for r in rows)
    require(
        corrected or not model("workload.TeacherAssignment").objects.filter(pk=p["new_assignment"]).exists(),
        "history636_new_assignment_collision",
    )
    require(len(rows) == (4 if corrected else 3), "history636_row_set_changed")
    for row in rows:
        if row["id"] in p["rows"]:
            require(
                same(row, row_after(p["rows"][row["id"]]) if corrected else p["rows"][row["id"]]),
                "history636_partial_or_changed_row",
            )
        else:
            require(same(row, new_row_values()), "history636_new_row_changed")
        expected = p["groups"] if row["id"] == p["new_row"] else [p["row_groups"][row["id"]]]
        found = sorted(
            map(str, model("workload.TeachingTaskRow").objects.get(pk=row["id"]).groups.values_list("pk", flat=True))
        )
        require(found == sorted(expected), "history636_group_links_changed")
    rivals = model("workload.TeachingTaskRow").objects.filter(
        organization=org, subject_id=p["subject_id"], period_id=spec.PERIOD, groups__pk__in=p["groups"]
    )
    require(set(map(str, rivals.values_list("pk", flat=True))) == {r["id"] for r in rows}, "history636_other_load_row")
    allocations = bounded(
        model("workload.TeacherAssignment").objects.filter(organization=org, row_id__in=[*p["rows"], p["new_row"]]),
        cap=6,
    )
    expected = assignment_after() if corrected else p["assignments"]
    require({a["id"] for a in allocations} == set(expected), "history636_assignment_set_changed")
    for a in allocations:
        require(same(a, expected[a["id"]]), "history636_assignment_changed")
    courses = bounded(model("registrar.CourseOffering").objects.filter(organization=org, pk__in=p["courses"]), cap=3)
    require(len(courses) == 3, "history636_courses_missing")
    for c in courses:
        require(
            same(c, {**p["courses"][c["id"]], **({"lesson_hours": 60} if corrected else {})}),
            "history636_course_changed",
        )
        require(
            model("registrar.CourseOffering")
            .objects.filter(organization=org, subject_id=p["subject_id"], period_id=spec.PERIOD, group_id=c["group_id"])
            .count()
            == 1,
            "history636_duplicate_course",
        )
    syllabi = bounded(model("syllabus.Syllabus").objects.filter(organization=org, pk__in=p["syllabi"]), cap=3)
    require(
        len(syllabi) == 3 and all(same(s, p["syllabi"][s["id"]]) for s in syllabi),
        "history636_syllabus_binding_changed",
    )
    versions = bounded(model("syllabus.SyllabusVersion").objects.filter(organization=org, pk__in=p["versions"]), cap=3)
    require(len(versions) == 3, "history636_versions_missing")
    for v in versions:
        pin = p["versions"][v["id"]]
        require(
            same(v, {k: pin[k] for k in ("syllabus_id", "status")})
            and v["plan_hours"] == pin["after_plan" if corrected else "plan_hours"],
            "history636_version_changed",
        )
        body = list(
            model("syllabus.SyllabusSection")
            .objects.filter(version_id=v["id"])
            .order_by("section_id")
            .values("section_id", "data")
        )
        require(digest(body) == pin["body_sha256"], "history636_approved_body_changed")
    raw = graph(
        spec.ORG,
        {
            "registrar.CourseOffering": p["courses"],
            "workload.TeachingTaskRow": [*p["rows"], p["new_row"]],
            "syllabus.Syllabus": p["syllabi"],
        },
    )
    return {
        "corrected": corrected,
        "rows": rows,
        "assignments": allocations,
        "courses": courses,
        "versions": versions,
        "academic": raw,
        "context": digest([periods, tasks, users, groups]),
    }


def new_row_values():
    p = spec.PINS
    base = copy.deepcopy(next(r for r in p["rows"].values() if r["task_id"] == p["task"]))
    base.update(
        id=p["new_row"],
        task_id=p["task"],
        lecture_plan=30,
        lecture_total=30,
        seminar_plan=0,
        seminar_total=0,
        total_hours=30,
        union_count=1,
        subgroup_count=1,
        student_count=76,
        groups_text="636/1 az + 636/2 az + 636/3 ing",
    )
    return base


def assignment_after():
    p = spec.PINS
    result = {a["id"]: {**a, "hours": 30} for a in p["assignments"].values() if a["activity"] == "seminar"}
    result[p["new_assignment"]] = {
        "id": p["new_assignment"],
        "row_id": p["new_row"],
        "teacher_id": p["teacher"],
        "activity": "lecture",
        "hours": 30,
        "is_hourly_paid": False,
    }
    return result


def protected(snapshot):
    p = spec.PINS
    raw = copy.deepcopy(snapshot["academic"])
    for label, values in raw.items():
        if label == "workload.TeachingTaskRow":
            raw[label] = [
                {
                    k: v
                    for k, v in r.items()
                    if k
                    not in {
                        "lecture_plan",
                        "lecture_total",
                        "seminar_plan",
                        "seminar_total",
                        "total_hours",
                        "union_count",
                    }
                }
                for r in values
                if r["id"] != p["new_row"]
            ]
        elif label == "workload.TeacherAssignment":
            raw[label] = [
                {k: v for k, v in r.items() if k != "hours"}
                for r in values
                if r["id"] in p["assignments"] and p["assignments"][r["id"]]["activity"] == "seminar"
            ]
            require(
                all(r["id"] in {*p["assignments"], p["new_assignment"]} for r in values),
                "history636_unknown_assignment",
            )
        elif label == "workload.TeachingTaskRow_groups":
            raw[label] = [r for r in values if r["teachingtaskrow_id"] != p["new_row"]]
        elif label == "registrar.CourseOffering":
            raw[label] = [{k: v for k, v in r.items() if k != "lesson_hours"} for r in values]
        elif label == "syllabus.SyllabusVersion":
            raw[label] = [
                {k: v for k, v in r.items() if k != "plan_hours" or r["id"] not in p["versions"]} for r in values
            ]
    return {
        "context": snapshot["context"],
        "graph": {k: {"count": len(v), "sha256": digest(v)} for k, v in raw.items()},
    }
