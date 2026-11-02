"""Fresh locked graph and exact source geometry, with no academic-content mutations."""

import copy

from apps.registrar.public import credit_source, schedule_lock

from . import reviewed_gunay_ethnography_spec as spec
from .people import is_assignable_teacher
from .reviewed_leyla_catalog_graph import bounded, digest, graph, model, require


def same(actual, expected):
    return all(actual.get(key) == value for key, value in expected.items())


def snapshot(org):
    pin = spec.PINS
    require(str(org.pk) == pin["organization_id"] and org.is_active, "gunay_organization_changed")
    schedule_lock.lock_schedule(org.pk, pin["period_id"])
    teacher = model("auth.User").objects.get(pk=pin["teacher"])
    chair = model("organizations.OrgUnit").objects.get(pk=pin["chair"], organization=org)
    require(is_assignable_teacher(org, chair, teacher), "gunay_teacher_permission_changed")
    rows = bounded(model("workload.TeachingTaskRow").objects.filter(organization=org, pk__in=pin["rows"]), cap=3)
    require({r["id"] for r in rows} == set(pin["rows"]), "gunay_exact_three_rows_required")
    modes = []
    for corrected in (False, True):
        expected = copy.deepcopy(pin["rows"])
        if corrected:
            for key, fields in pin["row_after"].items():
                expected[key].update(fields)
        modes.append(all(same(row, expected[row["id"]]) for row in rows))
    require(sum(modes) == 1, "gunay_partial_or_changed_rows")
    corrected = modes[1]
    task_ids = {r["task_id"] for r in rows}
    tasks = bounded(model("workload.TeachingTask").objects.filter(organization=org, pk__in=task_ids), cap=1)
    require(
        len(tasks) == 1 and tasks[0]["status"] in {"approved", "distributed", "amended"}, "gunay_released_task_required"
    )
    require(tasks[0]["chair_id"] == pin["chair"], "gunay_chair_changed")
    period = bounded(model("organizations.AcademicPeriod").objects.filter(organization=org, pk=pin["period_id"]), cap=1)
    require(len(period) == 1 and period[0]["is_active"] and not period[0]["locked_at"], "gunay_open_period_required")
    group_ids = set()
    for row in rows:
        ids = set(
            map(str, model("workload.TeachingTaskRow").objects.get(pk=row["id"]).groups.values_list("pk", flat=True))
        )
        require(ids == set(pin["groups"][row["id"]]), "gunay_group_identity_changed")
        group_ids.update(ids)
    rivals = model("workload.TeachingTaskRow").objects.filter(
        organization=org, subject_id=pin["subject"], period_id=pin["period_id"], groups__pk__in=group_ids
    )
    require(set(map(str, rivals.values_list("pk", flat=True))) == set(pin["rows"]), "gunay_other_official_row")
    assignments = bounded(
        model("workload.TeacherAssignment").objects.filter(organization=org, row_id__in=pin["rows"]), cap=6
    )
    expected = copy.deepcopy(pin["assignments"])
    if corrected:
        expected = {
            key: {**value, "hours": pin["after_hours"][key]}
            for key, value in expected.items()
            if key not in pin["removed"]
        }
    require({a["id"] for a in assignments} == set(expected), "gunay_assignment_ids_changed")
    require(all(same(a, expected[a["id"]]) for a in assignments), "gunay_assignment_identity_changed")
    require(sum(a["hours"] for a in assignments) == 60, "gunay_teacher_stream_total_changed")
    courses = bounded(
        model("registrar.CourseOffering")._base_manager.filter(organization=org, pk__in=pin["courses"]), cap=2
    )
    require({c["id"] for c in courses} == set(pin["courses"]), "gunay_exact_two_courses_required")
    for course in courses:
        expected_course = {**pin["courses"][course["id"]], **({"lesson_hours": 45} if corrected else {})}
        require(same(course, expected_course), "gunay_course_identity_or_hours_changed")
    require({c["group_id"] for c in courses} == group_ids, "gunay_course_groups_changed")
    all_courses = model("registrar.CourseOffering")._base_manager.filter(
        organization=org, subject_id=pin["subject"], period_id=pin["period_id"], group_id__in=group_ids
    )
    require(set(map(str, all_courses.values_list("pk", flat=True))) == set(pin["courses"]), "gunay_duplicate_course")
    academic = graph(str(org.pk), {"workload.TeachingTaskRow": pin["rows"], "registrar.CourseOffering": pin["courses"]})
    enrs = model("registrar.Enrollment").objects.filter(organization=org, offering_id__in=pin["courses"])
    credits = credit_source.credits_for_enrollments(enrs, organization=org)
    teacher_assignments = bounded(
        model("workload.TeacherAssignment").objects.filter(organization=org, teacher_id=pin["teacher"]), cap=100
    )
    return {
        "corrected": corrected,
        "rows": rows,
        "assignments": assignments,
        "courses": courses,
        "academic": academic,
        "credits": digest({str(k): v for k, v in credits.items()}),
        "context": digest(
            [
                tasks,
                period,
                bounded(model("organizations.OrgUnit").objects.filter(organization=org, pk__in=group_ids), cap=2),
            ]
        ),
        "other_teacher_assignments": digest([a for a in teacher_assignments if a["row_id"] not in pin["rows"]]),
    }


def protected(value):
    raw = copy.deepcopy(value["academic"])
    for label, rows in raw.items():
        if label == "workload.TeachingTaskRow":
            raw[label] = [{k: v for k, v in row.items() if k not in spec.PINS["row_after"][row["id"]]} for row in rows]
        elif label == "workload.TeacherAssignment":
            raw[label] = [
                {k: v for k, v in row.items() if k not in {"hours", "assigned_by_id", "updated_at"}}
                for row in rows
                if row["id"] not in spec.PINS["removed"]
            ]
        elif label == "registrar.CourseOffering":
            raw[label] = [{k: v for k, v in row.items() if k != "lesson_hours"} for row in rows]
    return {
        **{
            key: val
            for key, val in value.items()
            if key not in {"corrected", "rows", "assignments", "courses", "academic"}
        },
        "academic": raw,
    }
