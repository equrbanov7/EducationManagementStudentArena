"""Locked teacher allocations plus complete academic closure; fixed keeper prerequisite."""

import copy

from django.db import connection

from apps.registrar.public import schedule_lock

from . import reviewed_elshen_duplicates_spec as spec
from . import reviewed_two_catalog_schema as schema
from .reviewed_leyla_catalog_graph import bounded, graph, model, require


def total_hours(org):
    return sum(
        model("workload.TeacherAssignment")
        .objects.filter(organization=org, teacher_id=spec.PINS["teacher"], row__period_id=spec.PINS["period"])
        .values_list("hours", flat=True)
    )


def snapshot(org):
    pin = spec.PINS
    require(
        connection.vendor == "postgresql" and schema.fingerprints() == spec.SCHEMA, "elshen_postgresql_schema_required"
    )
    schedule_lock.lock_schedule(str(org.pk), pin["period"])
    period = model("organizations.AcademicPeriod").objects.get(pk=pin["period"], organization=org)
    require(
        period.is_active and period.is_current and period.locked_at is None, "elshen_current_unlocked_period_required"
    )
    user = model("auth.User").objects.get(pk=pin["teacher"], is_active=True)
    require(user.username == pin["teacher_username"], "elshen_teacher_identity_changed")
    rows = bounded(
        model("workload.TeachingTaskRow").objects.select_for_update().filter(organization=org, pk__in=pin["rows"])
    )
    require({r["id"] for r in rows} == set(pin["rows"]), "elshen_exact_ten_rows_required")
    assignments = bounded(
        model("workload.TeacherAssignment").objects.select_for_update().filter(organization=org, row_id__in=pin["rows"])
    )
    keeper_rows = (
        model("workload.TeachingTaskRow").objects.select_for_update().filter(organization=org, pk__in=pin["keepers"])
    )
    require(keeper_rows.count() == len(pin["keepers"]), "elshen_keeper_rows_required")
    for row in keeper_rows:
        keeper = pin["keepers"][str(row.pk)]
        require(
            set(map(str, row.groups.values_list("pk", flat=True))) == set(keeper["groups"]),
            "elshen_keeper_group_prerequisite_changed",
        )
        require(
            all(getattr(row, k) == v for k, v in keeper.items() if k != "groups"),
            "elshen_keeper_geometry_prerequisite_changed",
        )
        found = {(a.activity, a.teacher_id): a.hours for a in row.assignments.all()}
        require(
            found
            == {
                ("lecture", pin["teacher"]): keeper["lecture_total"],
                ("seminar", pin["teacher"]): keeper["seminar_total"],
            },
            "elshen_keeper_contributions_changed",
        )
    courses = list(
        model("registrar.CourseOffering")
        .objects.filter(organization=org, period_id=pin["period"], instructor_id=pin["teacher"])
        .values_list("pk", flat=True)
    )
    academic = graph(
        str(org.pk),
        {
            "workload.TeachingTaskRow": set(pin["rows"]) | set(pin["keepers"]),
            "registrar.CourseOffering": list(map(str, courses)),
        },
    )
    return {"rows": rows, "assignments": assignments, "academic": academic, "teacher_hours": total_hours(org)}


def protected(value):
    result = copy.deepcopy(value["academic"])
    allowed = {a["id"] for r in spec.PINS["rows"].values() for a in r["assignments"]}
    for label, rows in result.items():
        if label == "workload.TeacherAssignment":
            result[label] = [r for r in rows if r["id"] not in allowed]
        if label == "workload.TeachingTaskRow":
            for row in rows:
                if row["id"] in spec.PINS["rows"]:
                    for key in (*spec.ZERO, "updated_at"):
                        row.pop(key, None)
    return {key: rows for key, rows in result.items() if rows}
