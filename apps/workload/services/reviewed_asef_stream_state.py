"""Locked fixed source identity and full academic closure; no score/absence writes."""

import copy

from django.db import connection
from django.db.models import Q
from django.utils import timezone

from apps.registrar.public import credit_source, schedule_lock

from . import reviewed_asef_stream_spec as spec
from . import reviewed_two_catalog_schema as schema
from .people import is_assignable_teacher
from .reviewed_leyla_catalog_graph import bounded, digest, graph, model, require


def same(actual, expected, code):
    require(all(actual.get(key) == value for key, value in expected.items()), code)


def snapshot(org):
    pin = spec.PINS
    require(connection.vendor == "postgresql", "asef_postgresql_required")
    require(schema.fingerprints() == spec.SCHEMA, "asef_relation_schema_changed")
    schedule_lock.lock_schedule(spec.ORG, spec.PERIOD)
    period = bounded(model("organizations.AcademicPeriod").objects.filter(organization=org, pk=spec.PERIOD), cap=1)
    require(
        len(period) == 1
        and period[0]["is_active"]
        and period[0]["is_current"]
        and period[0]["locked_at"] is None
        and period[0]["academic_year"] == pin["year"]
        and period[0]["start_date"] <= timezone.localdate().isoformat() <= period[0]["end_date"],
        "asef_period_changed_or_locked",
    )
    tasks = bounded(model("workload.TeachingTask").objects.filter(organization=org, pk=pin["task"]), cap=1)
    require(len(tasks) == 1 and tasks[0]["status"] == "amended", "asef_released_amended_task_required")
    same(tasks[0], {k: pin["task_pin"][k] for k in ("id", "chair_id", "academic_year")}, "asef_task_changed")
    users = bounded(model("auth.User").objects.filter(pk=spec.TEACHER, is_active=True), cap=1)
    profiles = bounded(model("accounts.UserProfile").objects.filter(user_id=spec.TEACHER), cap=1)
    require(
        len(users) == len(profiles) == 1
        and [users[0]["first_name"], users[0]["last_name"], profiles[0]["patronymic"]] == pin["name"]
        and profiles[0]["organization_id"] == spec.ORG
        and not profiles[0]["is_deleted"]
        and profiles[0]["deleted_at"] is None
        and profiles[0]["blocked_at"] is None
        and profiles[0]["access_state"] == "active",
        "asef_teacher_identity_changed",
    )
    teacher = model("auth.User").objects.get(pk=spec.TEACHER)
    chair = model("organizations.OrgUnit").objects.get(pk=pin["chair"], organization=org)
    require(is_assignable_teacher(org, chair, teacher), "asef_teacher_permission_changed")
    groups = bounded(model("organizations.OrgUnit").objects.filter(organization=org, pk__in=pin["groups"]), cap=4)
    require({g["id"] for g in groups} == set(pin["groups"]), "asef_groups_missing")
    for group in groups:
        same(group, pin["groups"][group["id"]], "asef_group_or_parent_identity_changed")
    subject = bounded(model("registrar.Subject").objects.filter(organization=org, pk=pin["subject"]), cap=1)
    require(len(subject) == 1 and subject[0]["is_active"], "asef_active_subject_required")
    same(subject[0], pin["subject_pin"], "asef_subject_identity_changed")
    rows = bounded(model("workload.TeachingTaskRow").objects.filter(organization=org, pk__in=pin["row_before"]), cap=2)
    require({r["id"] for r in rows} == set(pin["row_before"]), "asef_exact_two_rows_required")
    states = []
    for corrected in (False, True):
        expected = copy.deepcopy(pin["row_before"])
        if corrected:
            for key, changes in pin["row_after"].items():
                expected[key].update(changes)
        states.append(all(all(r.get(k) == v for k, v in expected[r["id"]].items()) for r in rows))
    require(sum(states) == 1, "asef_partial_or_changed_row_state")
    corrected = states[1]
    expected_groups = pin["row_groups_after" if corrected else "row_groups_before"]
    for row in rows:
        found = list(
            map(
                str,
                model("workload.TeachingTaskRow")
                .objects.get(pk=row["id"])
                .groups.order_by("pk")
                .values_list("pk", flat=True),
            )
        )
        require(found == sorted(expected_groups[row["id"]]), "asef_official_row_groups_changed")
    group_ids = set(pin["groups"]) - {pin["bi_parent"]}
    rivals = model("workload.TeachingTaskRow").objects.filter(
        organization=org, period_id=spec.PERIOD, subject_id=pin["subject"], groups__pk__in=pin["groups"]
    )
    require(set(map(str, rivals.values_list("pk", flat=True))) == set(pin["row_before"]), "asef_other_official_row")
    assignments = bounded(
        model("workload.TeacherAssignment").objects.filter(organization=org, row_id__in=pin["row_before"]), cap=4
    )
    expected_assignments = copy.deepcopy(pin["assignments"])
    if corrected:
        expected_assignments = {
            k: {**v, "hours": 30} for k, v in expected_assignments.items() if v["row_id"] == spec.KEEPER
        }
    require({a["id"] for a in assignments} == set(expected_assignments), "asef_assignment_ids_changed")
    for assignment in assignments:
        same(assignment, expected_assignments[assignment["id"]], "asef_assignment_identity_changed")
    require(sum(a["hours"] for a in assignments) == 60, "asef_stream_teacher_hours_changed")
    all_assignments = bounded(
        model("workload.TeacherAssignment").objects.filter(
            organization=org, teacher_id=spec.TEACHER, row__period_id=spec.PERIOD
        ),
        cap=100,
    )
    require(sum(a["hours"] for a in all_assignments) == pin["teacher_fall_hours"], "asef_teacher_total_hours_changed")
    courses = bounded(
        model("registrar.CourseOffering")._base_manager.filter(organization=org, pk__in=pin["courses"]), cap=3
    )
    require({c["id"] for c in courses} == set(pin["courses"]), "asef_exact_three_journals_required")
    for course in courses:
        expected = {**pin["courses"][course["id"]], **({"lesson_hours": 60} if corrected else {})}
        same(course, expected, "asef_course_identity_or_contact_changed")
        require(course["course_format"] == "regular", "asef_regular_course_required")
        require(
            model("registrar.CourseOffering")
            ._base_manager.filter(
                organization=org, period_id=spec.PERIOD, subject_id=pin["subject"], group_id=course["group_id"]
            )
            .count()
            == 1,
            "asef_duplicate_course_requires_review",
        )
        for label, key in (("Lesson", "lessons"), ("LessonMark", "marks"), ("Enrollment", "enrollments")):
            lookup = "lesson__offering_id" if label == "LessonMark" else "offering_id"
            require(
                model("registrar." + label).objects.filter(**{lookup: course["id"]}).count()
                == pin["counts"][course["id"]][key],
                "asef_academic_counts_changed",
            )
    require({c["group_id"] for c in courses} == group_ids, "asef_exact_course_groups_required")
    require(
        not model("registrar.JournalShare")
        .objects.filter(organization=org, offering_id__in=pin["courses"], is_active=True)
        .exclude(teacher_id=spec.TEACHER)
        .exists(),
        "asef_other_teacher_share",
    )
    syllabi = bounded(model("syllabus.Syllabus").objects.filter(organization=org, pk__in=pin["syllabi"]), cap=3)
    require({s["id"] for s in syllabi} == set(pin["syllabi"]), "asef_own_approved_syllabus_required")
    for syllabus in syllabi:
        same(syllabus, pin["syllabi"][syllabus["id"]], "asef_own_syllabus_binding_changed")
    versions = bounded(
        model("syllabus.SyllabusVersion").objects.filter(organization=org, pk__in=pin["version_before"]), cap=3
    )
    require({v["id"] for v in versions} == set(pin["version_before"]), "asef_exact_approved_versions_required")
    for version in versions:
        expected = {**pin["version_before"][version["id"]], **({"plan_hours": spec.PLAN} if corrected else {})}
        same(version, expected, "asef_approved_version_metadata_changed")
        body = list(
            model("syllabus.SyllabusSection")
            .objects.filter(version_id=version["id"])
            .order_by("section_id")
            .values("section_id", "data")
        )
        require(digest(body) == pin["body_sha256"][version["id"]], "asef_source_body_changed")
    bridge_query = Q(pk__in=[])
    for b in pin["bridge"]:
        bridge_query |= Q(entity_type=b["entity_type"], legacy_pk=b["legacy_pk"])
    bridges = bounded(
        model("legacy_import.LegacyEntityMap").objects.filter(
            bridge_query, organization=org, source_system="myedu_mariadb"
        ),
        cap=3,
    )
    require(len(bridges) == len(pin["bridge"]), "asef_typed_source_bridge_changed")
    for expected in pin["bridge"]:
        require(
            any(all(b.get(k) == v for k, v in expected.items()) for b in bridges), "asef_typed_source_bridge_changed"
        )
    enrs = model("registrar.Enrollment").objects.filter(organization=org, offering_id__in=pin["courses"])
    credits = credit_source.credits_for_enrollments(enrs, organization=org)
    raw = graph(
        spec.ORG,
        {
            "registrar.CourseOffering": pin["courses"],
            "workload.TeachingTaskRow": pin["row_before"],
            "syllabus.Syllabus": pin["syllabi"],
        },
    )
    memberships = bounded(
        model("organizations.Membership").objects.filter(organization=org, user_id=spec.TEACHER), cap=20
    )
    return {
        "corrected": corrected,
        "rows": rows,
        "assignments": assignments,
        "courses": courses,
        "versions": versions,
        "academic": raw,
        "credits": digest({str(key): value for key, value in credits.items()}),
        "fixed_context": digest([period, tasks, users, profiles, groups, subject, bridges, memberships]),
        "other_assignments": digest([a for a in all_assignments if a["row_id"] not in pin["row_before"]]),
    }


def protected(value):
    raw = copy.deepcopy(value["academic"])
    for label, values in list(raw.items()):
        if label == "workload.TeachingTaskRow":
            raw[label] = [
                {k: v for k, v in row.items() if k not in spec.PINS["row_after"][row["id"]]} for row in values
            ]
        elif label == "workload.TeacherAssignment":
            raw[label] = [
                {k: v for k, v in row.items() if k not in {"hours", "assigned_by_id", "updated_at"}}
                for row in values
                if row["row_id"] != spec.DUPLICATE
            ]
        elif label == "registrar.CourseOffering":
            raw[label] = [{k: v for k, v in row.items() if k != "lesson_hours"} for row in values]
        elif label == "syllabus.SyllabusVersion":
            raw[label] = [
                {k: v for k, v in row.items() if not (row["id"] in spec.PINS["version_before"] and k == "plan_hours")}
                for row in values
            ]
        elif label == "workload.TeachingTaskRow_groups":
            added = set(spec.PINS["row_groups_after"][spec.KEEPER]) - set(spec.PINS["row_groups_before"][spec.KEEPER])
            raw[label] = [
                r for r in values if not (r["teachingtaskrow_id"] == spec.KEEPER and r["orgunit_id"] in added)
            ]
    return {
        "graph": {k: {"count": len(v), "sha256": digest(v)} for k, v in raw.items()},
        **{k: value[k] for k in ("credits", "fixed_context", "other_assignments")},
    }
