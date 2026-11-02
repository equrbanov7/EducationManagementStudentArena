"""Locked exact current workload, all current journal records and reverse history."""

import copy

from django.db import connection

from apps.registrar.public import schedule_lock

from . import reviewed_elshen_vacancy_spec as spec
from . import reviewed_two_catalog_schema as schema
from .reviewed_leyla_catalog_graph import bounded, digest, graph, model, require
from .scoping import ensure_can_distribute, ensure_can_manage, resolve_actor


def same(actual, expected):
    return all(actual.get(k) == v for k, v in expected.items())


def through():
    return model("workload.TeachingTaskRow").groups.through


def snapshot(org, user):
    p = spec.PINS
    require(connection.vendor == "postgresql" and schema.fingerprints() == spec.SCHEMA, "elshen_vacancy_schema_changed")
    schedule_lock.lock_schedule(spec.ORG, p["period"])
    period = model("organizations.AcademicPeriod").objects.select_for_update().get(pk=p["period"], organization=org)
    require(
        period.is_active and period.is_current and period.locked_at is None, "elshen_vacancy_current_period_required"
    )
    teacher = model("auth.User").objects.select_for_update().get(pk=p["teacher"])
    require(teacher.is_active and teacher.username == p["username"], "elshen_vacancy_teacher_changed")
    profile = model("accounts.UserProfile").objects.select_for_update().get(user=teacher)
    require(
        str(profile.organization_id) == spec.ORG
        and profile.access_state == "active"
        and not profile.is_deleted
        and profile.deleted_at is None
        and profile.blocked_at is None,
        "elshen_vacancy_teacher_inactive",
    )
    rows = bounded(model("workload.TeachingTaskRow").objects.filter(organization=org, pk__in=p["rows"]), cap=19)
    require({r["id"] for r in rows} == set(p["rows"]), "elshen_vacancy_exact_rows_required")
    tasks = bounded(
        model("workload.TeachingTask").objects.filter(organization=org, pk__in={r["task_id"] for r in rows}), cap=1
    )
    actor = resolve_actor(user, org)
    require(len(tasks) == 1 and tasks[0]["status"] == "amended", "elshen_vacancy_open_amendment_required")
    ensure_can_manage(actor, tasks[0]["chair_id"])
    ensure_can_distribute(actor, tasks[0]["chair_id"])
    assignments = bounded(
        model("workload.TeacherAssignment").objects.filter(organization=org, row_id__in=p["rows"]), cap=36
    )
    require({a["id"] for a in assignments} == set(p["assignments"]), "elshen_vacancy_assignment_set_changed")
    owners = {a["teacher_id"] for a in assignments if a["id"] in p["release"]}
    require(owners in ({p["teacher"]}, {None}), "elshen_vacancy_partial_release")
    corrected = owners == {None}
    for a in assignments:
        target = dict(p["assignments"][a["id"]])
        if corrected and a["id"] in p["release"]:
            target["teacher_id"] = None
        require(same(a, target), "elshen_vacancy_assignment_changed")
    links = bounded(through().objects.filter(teachingtaskrow_id__in=p["rows"]), cap=80)
    for r in rows:
        target = dict(p["rows"][r["id"]])
        wanted = p["groups"][r["id"]]
        if corrected and r["id"] == p["keeper"]:
            target["groups_text"] = "236 BİO, 236 BT"
            wanted = sorted(p["bt"] if gid == p["eko"] else gid for gid in wanted)
        require(same(r, target), "elshen_vacancy_row_geometry_changed")
        require(
            sorted(link["orgunit_id"] for link in links if link["teachingtaskrow_id"] == r["id"]) == wanted,
            "elshen_vacancy_group_mapping_changed",
        )
    annual = bounded(
        model("workload.TeacherAssignment").objects.filter(
            organization=org, teacher_id=p["teacher"], row__period_id=p["period"]
        ),
        cap=36,
    )
    expected_ids = set(p["assignments"]) - (set(p["release"]) if corrected else set())
    require(
        {a["id"] for a in annual} == expected_ids and sum(a["hours"] for a in annual) == (540 if corrected else 885),
        "elshen_vacancy_total_changed",
    )
    courses = bounded(model("registrar.CourseOffering").objects.filter(organization=org, pk__in=p["courses"]), cap=30)
    require({c["id"] for c in courses} == set(p["courses"]), "elshen_vacancy_course_set_changed")
    for c in courses:
        target = {**p["courses"][c["id"]]}
        if corrected and c["id"] == p["eko_course"]:
            target["instructor_id"] = None
        require(same(c, target), "elshen_vacancy_course_changed")
    academic = graph(spec.ORG, {"workload.TeachingTaskRow": p["rows"], "registrar.CourseOffering": p["courses"]})
    groups = bounded(
        model("organizations.OrgUnit").objects.filter(
            organization=org, pk__in={p["eko"], p["bt"]} | {g for gs in p["groups"].values() for g in gs}
        ),
        cap=40,
    )
    require({p["eko"], p["bt"]} <= {g["id"] for g in groups}, "elshen_vacancy_target_group_missing")
    return {
        "corrected": corrected,
        "rows": rows,
        "assignments": assignments,
        "links": links,
        "courses": courses,
        "academic": academic,
        "context": digest([tasks, groups]),
    }


def protected(value):
    p = spec.PINS
    raw = copy.deepcopy(value["academic"])
    label = through()._meta.label
    for name, rows in raw.items():
        for row in rows:
            if name == "workload.TeacherAssignment" and row["id"] in p["release"]:
                row.pop("teacher_id")
            elif name == "registrar.CourseOffering" and row["id"] == p["eko_course"]:
                row.pop("instructor_id")
            elif name == "workload.TeachingTaskRow" and row["id"] == p["keeper"]:
                row.pop("groups_text")
            elif (
                name == label and row["teachingtaskrow_id"] == p["keeper"] and row["orgunit_id"] in {p["eko"], p["bt"]}
            ):
                row.pop("orgunit_id")
    return {"context": value["context"], "graph": raw}
