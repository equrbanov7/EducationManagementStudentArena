"""Lock one existing60h allocation and its entire academic closure, preserving all history."""

import copy
import json
from pathlib import Path

from django.db import connection
from django.db.models import Q

from apps.registrar.public import handover, schedule_lock

from . import reviewed_consumer_handover_spec as spec
from .people import is_assignable_teacher
from .reviewed_ilahe_subject_state import actor_scope as validate_actor
from .reviewed_leyla_catalog_graph import RepairError, bounded, graph, model, require
from .scoping import ensure_can_distribute, resolve_actor

PINS = json.loads(Path(__file__).with_name("reviewed_consumer_handover_pins.json").read_text())


def actor_scope(organization, actor):
    require(connection.vendor == "postgresql", "consumer_postgresql_required")
    require(str(organization.pk) == spec.ORG, "consumer_fixed_tenant_required")
    try:
        validate_actor(organization, actor)
        ensure_can_distribute(resolve_actor(actor, organization), spec.CHAIR)
    except Exception:
        raise RepairError("consumer_actor_scope_refused") from None
    schedule_lock.lock_schedule(spec.ORG, spec.PERIOD)


def snapshot(*, allowed_handover=None):
    course = (
        model("registrar.CourseOffering")
        .objects.select_for_update(of=("self",))
        .select_related("period", "group")
        .filter(pk=spec.COURSE)
        .first()
    )
    require(course is not None, "consumer_fixed_course_required")
    require(
        str(course.organization_id) == spec.ORG
        and str(course.subject_id) == spec.SUBJECT
        and str(course.group_id) == spec.GROUP
        and str(course.period_id) == spec.PERIOD
        and course.is_active
        and not course.is_intensive
        and course.lesson_hours == 60
        and course.instructor_id in (spec.OLD, spec.NEW)
        and course.period.is_active
        and course.period.is_current
        and course.period.locked_at is None
        and course.period.organization_id == course.organization_id
        and course.group.is_active
        and course.group.organization_id == course.organization_id,
        "consumer_course_identity_changed",
    )
    row = (
        model("workload.TeachingTaskRow")
        .objects.select_for_update(of=("self",))
        .select_related("task")
        .filter(pk=spec.ROW)
        .first()
    )
    require(
        row is not None
        and str(row.organization_id) == spec.ORG
        and str(row.task_id) == spec.TASK
        and str(row.task.chair_id) == spec.CHAIR
        and str(row.task.organization_id) == spec.ORG
        and row.task.status == "amended"
        and row.task.academic_year == "2026/2027"
        and str(row.subject_id) == spec.SUBJECT
        and str(row.period_id) == spec.PERIOD
        and row.row_kind == "teaching"
        and row.season == "fall"
        and row.lecture_plan == row.lecture_total == row.seminar_plan == row.seminar_total == 30
        and row.lab_plan == row.lab_total == 0
        and {str(k) for k in row.groups.values_list("pk", flat=True)} == {spec.GROUP},
        "consumer_fixed_allocation_changed",
    )
    other_rows = (
        model("workload.TeachingTaskRow")
        .objects.filter(organization_id=spec.ORG, subject_id=spec.SUBJECT, period_id=spec.PERIOD, groups__pk=spec.GROUP)
        .exclude(pk=spec.ROW)
    )
    require(
        not model("workload.TeacherAssignment").objects.filter(row__in=other_rows, hours__gt=0).exists(),
        "consumer_other_positive_allocation",
    )
    assignments = bounded(model("workload.TeacherAssignment").objects.filter(row_id=spec.ROW))
    require(
        {r["id"] for r in assignments} == set(spec.ASSIGNMENTS)
        and all(
            r["teacher_id"] == course.instructor_id
            and r["hours"] == 30
            and r["activity"] == spec.ASSIGNMENTS[r["id"]]
            and not r["is_hourly_paid"]
            and str(r["organization_id"]) == spec.ORG
            for r in assignments
        ),
        "consumer_assignment_identity_changed",
    )
    users = bounded(model("auth.User").objects.filter(pk__in=(spec.OLD, spec.NEW)))
    profiles = bounded(model("accounts.UserProfile").objects.filter(user_id__in=(spec.OLD, spec.NEW)))
    require(len(users) == len(profiles) == 2, "consumer_two_live_teachers_required")
    by_user = {p["user_id"]: p for p in profiles}
    for user in users:
        profile = by_user[user["id"]]
        require(
            user["is_active"]
            and (user["first_name"], user["last_name"], profile["patronymic"]) == spec.NAMES[user["id"]]
            and profile["organization_id"] == spec.ORG
            and not profile["is_deleted"]
            and profile["deleted_at"] is None
            and profile["blocked_at"] is None
            and profile["access_state"] == "active",
            "consumer_teacher_identity_changed",
        )
    require(
        all(
            is_assignable_teacher(course.organization, row.task.chair, model("auth.User").objects.get(pk=pk))
            for pk in (spec.OLD, spec.NEW)
        ),
        "consumer_teacher_not_assignable",
    )
    require(
        not model("registrar.JournalShare").objects.filter(offering_id=spec.COURSE, is_active=True).exists(),
        "consumer_active_share_requires_review",
    )
    handovers = bounded(model("registrar.TeachingHandover").objects.filter(offering_id=spec.COURSE))
    require(
        {r["id"] for r in handovers} == ({allowed_handover} if allowed_handover else set()), "consumer_unknown_handover"
    )
    if handovers:
        event = handovers[0]
        require(
            event["from_instructor_id"] == spec.OLD
            and event["to_instructor_id"] == spec.NEW
            and not event["deactivated_share_ids"]
            and bool(event["reverted_at"]) == (course.instructor_id == spec.OLD),
            "consumer_handover_identity_changed",
        )
    require(not handover.closed_offering_ids([course.pk]), "consumer_closed_journal")
    students = (
        model("registrar.Enrollment").objects.filter(offering_id=spec.COURSE).values_list("student_id", flat=True)
    )
    academic_records = (
        model("registrar.StudentAcademicRecord")
        ._base_manager.filter(organization_id=spec.ORG, student_id__in=students)
        .values_list("pk", flat=True)
    )
    data = graph(
        spec.ORG,
        {
            "registrar.CourseOffering": [spec.COURSE],
            "workload.TeachingTaskRow": [spec.ROW],
            "registrar.StudentAcademicRecord": list(academic_records),
        },
    )
    require(
        all(len(data.get(label, [])) == count for label, count in spec.COUNTS.items()), "consumer_fresh_counts_changed"
    )
    bridge = bounded(
        model("legacy_import.LegacyEntityMap")._base_manager.filter(
            Q(entity_type__in=("worker", "worker_materialisation"), legacy_pk__in=("613", "774"))
            | Q(entity_type="group_unit", legacy_pk="657")
            | Q(entity_type="lesson_subject", legacy_pk="1478"),
            organization_id=spec.ORG,
        )
    )
    require(
        len(bridge) == len(PINS["bridge"])
        and all(any(all(row.get(k) == value for k, value in pin.items()) for row in bridge) for pin in PINS["bridge"]),
        "consumer_source_bridge_changed",
    )
    references = {
        "source_bridge": bridge,
        "users": users,
        "profiles": profiles,
        "task": bounded(model("workload.TeachingTask").objects.filter(pk=spec.TASK)),
        "group": bounded(model("organizations.OrgUnit").objects.filter(pk=spec.GROUP)),
        "subject": bounded(model("registrar.Subject").objects.filter(pk=spec.SUBJECT)),
        "period": bounded(model("organizations.AcademicPeriod").objects.filter(pk=spec.PERIOD)),
        "memberships": bounded(
            model("organizations.Membership").objects.filter(organization_id=spec.ORG, user_id__in=(spec.OLD, spec.NEW))
        ),
    }
    return {"graph": data, "references": references, "corrected": course.instructor_id == spec.NEW}


def protected(value, *, handover_id=None):
    result = copy.deepcopy(value)
    result.pop("corrected")
    data = result["graph"]
    for row in data["registrar.CourseOffering"]:
        row.pop("instructor_id")
    for row in data["workload.TeacherAssignment"]:
        for field in ("teacher_id", "assigned_by_id", "updated_at"):
            row.pop(field)
    if "registrar.TeachingHandover" in data:
        data["registrar.TeachingHandover"] = [r for r in data["registrar.TeachingHandover"] if r["id"] != handover_id]
        if not data["registrar.TeachingHandover"]:
            data.pop("registrar.TeachingHandover")
    return result
