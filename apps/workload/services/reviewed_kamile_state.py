"""Exact13existing rows, vacancies and complete academic closure, never a workbook import."""

import copy

from django.db import connection

from apps.registrar.public import schedule_lock

from . import reviewed_kamile_spec as spec
from . import reviewed_two_catalog_schema as schema
from .group_projection import project_group_settings
from .people import is_assignable_teacher
from .queries import _visible_q
from .reviewed_leyla_catalog_graph import bounded, digest, graph, model, require
from .scoping import ensure_can_distribute, resolve_actor


def same(row, pin):
    return all(row.get(k) == v for k, v in pin.items())


def snapshot(org, user):
    p = spec.PINS
    require(connection.vendor == "postgresql" and schema.fingerprints() == spec.SCHEMA, "kamile_schema_changed")
    period_ids = {r["period_id"] for r in p["rows"].values()}
    for pid in sorted(period_ids):
        schedule_lock.lock_schedule(spec.ORG, pid)
    periods = bounded(model("organizations.AcademicPeriod").objects.filter(organization=org, pk__in=period_ids), cap=2)
    require(
        len(periods) == 2
        and all(r["is_active"] and r["locked_at"] is None and r["academic_year"] == p["year"] for r in periods),
        "kamile_period_changed",
    )
    tasks = bounded(model("workload.TeachingTask").objects.filter(organization=org, pk__in=p["tasks"]), cap=1)
    require(
        len(tasks) == 1 and all(same(t, p["tasks"][t["id"]]) and t["status"] == "amended" for t in tasks),
        "kamile_task_changed",
    )
    actor = resolve_actor(user, org)
    for task in tasks:
        ensure_can_distribute(actor, task["chair_id"])
    users = bounded(model("auth.User").objects.filter(pk=p["teacher"], is_active=True), cap=1)
    profiles = bounded(model("accounts.UserProfile").objects.filter(user_id=p["teacher"]), cap=1)
    identity = p["teacher_identity"]
    require(
        len(users) == len(profiles) == 1
        and same(users[0], {k: identity[k] for k in ["id", "username", "first_name", "last_name", "is_active"]})
        and profiles[0]["patronymic"] == identity["patronymic"]
        and profiles[0]["organization_id"] == spec.ORG
        and not profiles[0]["is_deleted"]
        and profiles[0]["deleted_at"] is None
        and profiles[0]["blocked_at"] is None
        and profiles[0]["access_state"] == "active",
        "kamile_teacher_identity_changed",
    )
    teacher = model("auth.User").objects.get(pk=p["teacher"])
    require(
        all(
            is_assignable_teacher(
                org, model("organizations.OrgUnit").objects.get(pk=t["chair_id"], organization=org), teacher
            )
            for t in tasks
        ),
        "kamile_teacher_scope_changed",
    )
    groups = bounded(model("organizations.OrgUnit").objects.filter(organization=org, pk__in=p["groups"]), cap=12)
    require(
        {g["id"] for g in groups} == set(p["groups"])
        and all(
            same(
                {**g, "settings": project_group_settings(g["settings"], canonical_group_ids=p["groups"])},
                p["groups"][g["id"]],
            )
            for g in groups
        ),
        "kamile_group_identity_changed",
    )
    subjects = bounded(model("registrar.Subject").objects.filter(organization=org, pk__in=p["subjects"]), cap=12)
    require(
        {s["id"] for s in subjects} == set(p["subjects"])
        and all(same(s, p["subjects"][s["id"]]) and s["is_active"] for s in subjects),
        "kamile_subject_changed",
    )
    rows = bounded(model("workload.TeachingTaskRow").objects.filter(organization=org, pk__in=p["rows"]), cap=13)
    require({r["id"] for r in rows} == set(p["rows"]), "kamile_row_set_changed")
    assignments = bounded(
        model("workload.TeacherAssignment").objects.filter(organization=org, row_id__in=p["rows"]), cap=30
    )
    ids = {a["id"] for a in assignments}
    if ids == set(p["assignments_before"]):
        corrected = False
    elif ids == set(p["assignments_after"]):
        corrected = True
    else:
        require(False, "kamile_partial_assignment_state")
    new_ids = set(p["assignments_after"]) - set(p["assignments_before"])
    require(
        corrected or not model("workload.TeacherAssignment").objects.filter(pk__in=new_ids).exists(),
        "kamile_new_vacancy_id_collision",
    )
    wanted = p["assignments_after" if corrected else "assignments_before"]
    require(all(same(a, wanted[a["id"]]) for a in assignments), "kamile_assignment_changed")
    for r in rows:
        expected = {**p["rows"][r["id"]], **(p["row_changes"].get(r["id"], {}) if corrected else {})}
        require(same(r, expected), "kamile_row_geometry_changed")
        actual = sorted(
            map(str, model("workload.TeachingTaskRow").objects.get(pk=r["id"]).groups.values_list("pk", flat=True))
        )
        require(actual == p["row_groups"][r["id"]], "kamile_row_group_changed")
    annual = bounded(
        model("workload.TeacherAssignment")
        .objects.filter(organization=org, teacher_id=p["teacher"], row__task__academic_year=p["year"])
        .filter(_visible_q()),
        cap=80,
    )
    require(
        {a["id"] for a in annual} == {a["id"] for a in wanted.values() if a["teacher_id"] == p["teacher"]}
        and sum(a["hours"] for a in annual) == (522 if corrected else 735),
        "kamile_annual_inventory_changed",
    )
    courses = bounded(model("registrar.CourseOffering").objects.filter(organization=org, pk__in=p["courses"]), cap=13)
    require({c["id"] for c in courses} == set(p["courses"]), "kamile_course_set_changed")
    for c in courses:
        changes = {"instructor_id": p["teacher"]} if corrected and c["id"] in p["owner_changes"] else {}
        require(same(c, {**p["courses"][c["id"]], **changes}), "kamile_course_identity_changed")
        require(
            model("registrar.CourseOffering")
            .objects.filter(
                organization=org, subject_id=c["subject_id"], period_id=c["period_id"], group_id=c["group_id"]
            )
            .count()
            == 1,
            "kamile_duplicate_course_requires_review",
        )
    syllabi = bounded(model("syllabus.Syllabus").objects.filter(organization=org, pk__in=p["syllabi"]), cap=6)
    require(
        {s["id"] for s in syllabi} == set(p["syllabi"]) and all(same(s, p["syllabi"][s["id"]]) for s in syllabi),
        "kamile_syllabus_binding_changed",
    )
    raw = graph(
        spec.ORG,
        {
            "registrar.CourseOffering": p["courses"],
            "workload.TeachingTaskRow": p["rows"],
            "syllabus.Syllabus": p["syllabi"],
        },
    )
    memberships = bounded(
        model("organizations.Membership").objects.filter(organization=org, user_id=p["teacher"]), cap=30
    )
    return {
        "corrected": corrected,
        "rows": rows,
        "assignments": assignments,
        "courses": courses,
        "academic": raw,
        "context": digest([periods, tasks, users, profiles, groups, subjects, memberships]),
    }


def protected(value):
    p = spec.PINS
    raw = copy.deepcopy(value["academic"])
    changed = {
        aid: {k for k, v in target.items() if p["assignments_before"].get(aid, {}).get(k) != v}
        for aid, target in p["assignments_after"].items()
        if aid in p["assignments_before"]
    }
    new = set(p["assignments_after"]) - set(p["assignments_before"])
    for label, rows in raw.items():
        if label == "workload.TeachingTaskRow":
            raw[label] = [
                {k: v for k, v in row.items() if k not in p["row_changes"].get(row["id"], {})} for row in rows
            ]
        elif label == "workload.TeacherAssignment":
            raw[label] = [
                {k: v for k, v in row.items() if k not in changed.get(row["id"], set())}
                for row in rows
                if row["id"] not in new
            ]
        elif label == "registrar.CourseOffering":
            raw[label] = [
                {k: v for k, v in row.items() if not (k == "instructor_id" and row["id"] in p["owner_changes"])}
                for row in rows
            ]
    return {"context": value["context"], "graph": {k: {"count": len(v), "sha256": digest(v)} for k, v in raw.items()}}
