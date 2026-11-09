"""Locked full-column bounded graph and canonical direct-carry/credit scenarios."""

import copy
import hashlib
import json
from decimal import Decimal

from django.apps import apps
from django.db.models import Q

from core.reviewed_graph import digest, graph, require, rows

from . import reaudit_journal_structure_spec as spec
from .absence_credit_read import credit_hours_map
from .enrollment_history import predecessors
from .models import CourseOffering, Enrollment, Lesson, LessonMark, ScheduleSlot
from .schedule_lock import lock_schedule


def actor_scope(organization, actor):
    require(str(organization.pk) == spec.ORG, "structure_actor_tenant")
    require(
        apps.get_model("organizations.Organization")
        .objects.select_for_update()
        .filter(pk=spec.ORG, is_active=True, status="active")
        .exists(),
        "structure_active_tenant",
    )
    require(
        apps.get_model("auth.User")
        .objects.select_for_update()
        .filter(pk=actor.pk, is_active=True, is_superuser=True)
        .exists(),
        "structure_active_superuser",
    )
    require(
        apps.get_model("accounts.UserProfile")
        .objects.select_for_update()
        .filter(
            user_id=actor.pk,
            organization_id=spec.ORG,
            access_state="active",
            is_deleted=False,
            deleted_at__isnull=True,
            blocked_at__isnull=True,
        )
        .exists(),
        "structure_actor_profile",
    )
    period = apps.get_model("organizations.AcademicPeriod").objects.select_for_update().get(pk=spec.PERIOD)
    require(
        str(period.organization_id) == spec.ORG and period.is_active and period.is_current and period.locked_at is None,
        "structure_current_unlocked_period",
    )
    return period


def family_for(organization, manifest):
    target = manifest["target_ids"]
    operation = manifest["operation"]
    if operation == "half_pair":
        targets = list(Lesson.objects.filter(organization=organization, pk__in=target).order_by("pk"))
        require(len(targets) == len(target), "structure_target_missing")
        roots = {lesson.offering_id for lesson in targets}
        enrollment_ids = set(
            LessonMark.objects.filter(organization=organization, lesson_id__in=target).values_list(
                "enrollment_id", flat=True
            )
        )
    elif operation == "park_inactive_slots":
        targets = list(
            ScheduleSlot.all_objects.filter(organization=organization, pk__in=target)
            .select_related("offering")
            .order_by("pk")
        )
        require(len(targets) == len(target), "structure_parking_slot_missing")
        require(
            all(not row.offering.is_active and not row.is_deleted for row in targets),
            "structure_parking_offering_now_active_or_deleted",
        )
        roots, enrollment_ids = {row.offering_id for row in targets}, set()
    elif operation in {"inactive_cache", "duplicate_qb"}:
        targets = list(
            Enrollment.objects.filter(organization=organization, pk__in=target)
            .select_related("offering")
            .order_by("pk")
        )
        require(len(targets) == len(target), "structure_target_missing")
        if operation == "inactive_cache":
            require(
                all(not row.offering.is_active and row.status != "enrolled" for row in targets),
                "structure_cache_target_now_active",
            )
        roots = {row.offering_id for row in targets}
        enrollment_ids = {row.pk for row in targets}
    else:
        targets = list(CourseOffering.objects.filter(organization=organization, pk__in=target).order_by("pk"))
        require(len(targets) == len(target) and all(row.is_active for row in targets), "structure_active_courses")
        roots, enrollment_ids = {row.pk for row in targets}, set()
    own = Enrollment.objects.filter(organization=organization, pk__in=enrollment_ids)
    require(own.count() == len(enrollment_ids), "structure_mark_enrollment_tenant")
    pairs = Q(pk__in=[])
    for row in own.select_related("offering"):
        pairs |= Q(
            student_id=row.student_id,
            offering__subject_id=row.offering.subject_id,
            offering__period_id=row.offering.period_id,
        )
    family = list(Enrollment.objects.filter(pairs, organization=organization).order_by("pk"))
    require(len(family) <= 500, "structure_family_budget")
    roots |= {row.offering_id for row in family}
    require(len(roots) <= 40, "structure_course_budget")
    courses = list(CourseOffering.objects.filter(organization=organization, pk__in=roots).order_by("pk"))
    require(
        len(courses) == len(roots) and all(str(row.period_id) == spec.PERIOD for row in courses),
        "structure_course_period",
    )
    family_ids = {row.pk for row in family}
    require(
        all(row.superseded_by_id is None or row.superseded_by_id in family_ids for row in family),
        "structure_history_outside_family",
    )
    incoming = Enrollment.objects.filter(organization=organization, superseded_by_id__in=family_ids)
    require(not incoming.exclude(pk__in=family_ids).exists(), "structure_incoming_history_outside_family")
    valid = set(predecessors().filter(organization=organization, pk__in=family_ids).values_list("pk", flat=True))
    require(all(row.superseded_by_id is None or row.pk in valid for row in family), "structure_invalid_history")
    affected = set(enrollment_ids)
    while True:
        more = {row.superseded_by_id for row in family if row.pk in affected and row.pk in valid} - affected - {None}
        if not more:
            break
        affected |= more
    if operation == "inactive_cache":
        require(
            all(
                not next(c for c in courses if c.pk == row.offering_id).is_active and row.status != "enrolled"
                for row in family
                if row.pk in affected
            ),
            "structure_cache_reaches_active_target",
        )
    return courses, family, affected


def capture(organization, actor, manifest):
    period = actor_scope(organization, actor)
    lock_schedule(organization.pk, period.pk)
    courses, family, affected = family_for(organization, manifest)
    roots = {"registrar.CourseOffering": [row.pk for row in courses]}
    captured = graph(roots, organization_id=organization.pk)
    course_ids = {str(row.pk) for row in courses}
    require(
        all(row["offering_id"] in course_ids for row in captured.get("registrar.Enrollment", [])),
        "structure_graph_cross_course_history",
    )
    student_ids = {row.student_id for row in family}
    extra = {
        "period": rows(type(period).objects.filter(pk=period.pk)),
        "groups": rows(
            apps.get_model("organizations.OrgUnit").objects.filter(
                organization=organization, pk__in=[row.group_id for row in courses]
            )
        ),
        "subjects": rows(
            apps.get_model("registrar.Subject").objects.filter(
                organization=organization, pk__in=[row.subject_id for row in courses]
            )
        ),
        "student_records": rows(
            apps.get_model("registrar.StudentAcademicRecord").objects.filter(
                organization=organization, student_id__in=student_ids
            )
        ),
    }
    room_ids = {row["room_id"] for row in captured.get("registrar.Lesson", []) if row.get("room_id")}
    extra["rooms"] = rows(apps.get_model("exams.ExamRoom").objects.filter(organization=organization, pk__in=room_ids))
    # Workload reference evidence is read-only, including released status/geometry and overrides.
    workload = apps.get_model("workload.TeachingTaskRow").objects.filter(
        organization=organization, period=period, subject_id__in=[row.subject_id for row in courses]
    )
    extra["workload"] = graph(
        {"workload.TeachingTaskRow": workload.values_list("pk", flat=True)}, organization_id=organization.pk
    )
    task_ids = workload.values_list("task_id", flat=True)
    extra["tasks"] = rows(
        apps.get_model("workload.TeachingTask").objects.filter(organization=organization, pk__in=task_ids)
    )
    if manifest["operation"] in {"timetable", "park_inactive_slots"}:
        extra["period_slots"] = rows(
            ScheduleSlot.all_objects.filter(organization=organization, offering__period=period)
        )
    if manifest["operation"] == "park_inactive_slots":
        # Effective teachers/groups belong to headers, not only the slot rows.
        extra["period_slot_offerings"] = rows(
            CourseOffering.objects.filter(
                organization=organization, pk__in={row["offering_id"] for row in extra["period_slots"]}
            )
        )
    family_ids = {str(row.pk) for row in family}
    current_enrollments = {
        row["id"]: row for row in captured.get("registrar.Enrollment", []) if row["id"] in family_ids
    }
    marks = [row for row in captured.get("registrar.LessonMark", []) if row["enrollment_id"] in family_ids]
    lessons = {row["id"]: row for row in captured.get("registrar.Lesson", [])}
    require(
        all(
            row["lesson_id"] in lessons
            and lessons[row["lesson_id"]]["offering_id"] == current_enrollments[row["enrollment_id"]]["offering_id"]
            for row in marks
        ),
        "structure_mark_reference_conflict",
    )
    credit = {str(pk): value for pk, value in credit_hours_map([row.pk for row in family]).items()}
    scenario = counters(current_enrollments, marks, lessons, credit, manifest)
    return {"graph": captured, "extra": extra, "affected_ids": sorted(map(str, affected)), "preview": scenario}


def counters(enrollments, marks, lessons, credits, manifest):
    old, delta, incoming = {}, {}, {}
    for row in enrollments.values():
        if row["status"] == "dropped" and row["superseded_by_id"]:
            incoming.setdefault(row["superseded_by_id"], []).append(row["id"])
    for mark in marks:
        if mark["status"] != "absent":
            continue
        eid, lesson = mark["enrollment_id"], lessons[mark["lesson_id"]]
        old[eid] = old.get(eid, 0) + lesson["hours"]
        if manifest["operation"] == "half_pair" and lesson["id"] in manifest["target_ids"]:
            delta[eid] = delta.get(eid, 0) + 1 - lesson["hours"]

    def derived(eid, after):
        raw = old.get(eid, 0) + (delta.get(eid, 0) if after else 0)
        carry = sum(
            max(0, old.get(p, 0) + (delta.get(p, 0) if after else 0) - credits.get(p, 0)) for p in incoming.get(eid, [])
        )
        return max(0, raw + carry - credits.get(eid, 0))

    return [
        {
            "enrollment_id": eid,
            "cached": row["absence_hours"],
            "canonical_before": derived(eid, False),
            "canonical_after": derived(eid, True),
            "credit_hours": credits.get(eid, 0),
            "direct_predecessor_ids": sorted(incoming.get(eid, [])),
        }
        for eid, row in sorted(enrollments.items())
    ]


def half_pair_pins(snapshot, *, hours):
    data = snapshot["graph"]
    for case in spec.scope()["half_pair_cases"]:
        for label, pk, fields, expected in (
            ("registrar.CourseOffering", case["offering_id"], case["offering_fields"], case["offering_sha256"]),
            ("registrar.Lesson", case["lesson_id"], case["lesson_fields"], case["lesson_sha256"]),
        ):
            row = next((r for r in data[label] if r["id"] == pk), None)
            require(row is not None, "structure_half_pair_missing")
            require(digest({key: str(row[key]) for key in fields}) == expected, "structure_half_pair_identity_changed")
        lesson = next(r for r in data["registrar.Lesson"] if r["id"] == case["lesson_id"])
        require(lesson["hours"] == hours, "structure_half_pair_hours_changed")
        pins = sorted(
            (
                r["id"],
                r["enrollment_id"],
                r["status"],
                format(Decimal(str(r["score"])).normalize(), "f") if r["score"] is not None else None,
                r["entered_by_id"],
            )
            for r in data.get("registrar.LessonMark", [])
            if r["lesson_id"] == lesson["id"]
        )
        encoded = json.dumps(pins, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode()
        require(
            len(pins) == case["mark_count"] and hashlib.sha256(encoded).hexdigest() == case["marks_sha256"],
            "structure_half_pair_reviewed_marks_changed",
        )


def protected(snapshot, manifest, *, correction_ids=(), reversal_ids=(), slot_ids=()):
    value = copy.deepcopy(snapshot)
    value.pop("preview")
    data = value["graph"]
    for row in data.get("registrar.Enrollment", []):
        if row["id"] in value["affected_ids"]:
            row.pop("absence_hours", None)
    if manifest["operation"] == "half_pair":
        for row in data.get("registrar.Lesson", []):
            if row["id"] in manifest["target_ids"]:
                row.pop("hours", None)
                row.pop("updated_at", None)
    if manifest["operation"] == "park_inactive_slots":
        from .reaudit_journal_structure_parking import protect

        protect(value, manifest)
    for label, ids in (
        ("registrar.LessonCorrection", correction_ids),
        ("registrar.CorrectionReversal", reversal_ids),
        ("registrar.ScheduleSlot", slot_ids),
    ):
        if label in data:
            data[label] = [row for row in data[label] if str(row["id"]) not in ids]
            if not data[label]:
                data.pop(label)
    if "period_slots" in value["extra"]:
        value["extra"]["period_slots"] = [row for row in value["extra"]["period_slots"] if row["id"] not in slot_ids]
    return value
