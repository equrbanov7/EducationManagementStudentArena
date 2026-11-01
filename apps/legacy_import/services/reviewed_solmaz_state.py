"""Locked exact identity and full reverse closure; receipts contain hashes, never grades."""

import copy
import datetime

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.utils import timezone

from apps.registrar.public import credit_source, eligible_instructor_user_ids, schedule_lock
from apps.syllabus.public import approved_version_for, content_fingerprints, section_data_map, syllabus_for_offering
from apps.workload.public import plan_reached_chair
from apps.workload.public import reviewed_catalog_graph as e
from apps.workload.public import reviewed_catalog_schema

from . import reviewed_solmaz_spec as spec
from .blank_draft_syllabus_state import actor_scope


def require_pins(rows, pins, code):
    actual = {r["id"]: r for r in rows}

    def matches(value, expected, field):
        # Old standard exports declare millisecond precision. Full current
        # microseconds stay in protected_graph and before/after/undo receipts.
        if field == "locked_at" and isinstance(expected, str) and "T" in expected and value:
            value = DjangoJSONEncoder().default(datetime.datetime.fromisoformat(value))
        return value == expected

    e.require(
        set(actual) == set(pins)
        and all(all(matches(actual[pk][k], v, k) for k, v in pin.items()) for pk, pin in pins.items()),
        code,
    )


def bridges(org):
    query = Q(pk__in=[])
    for pin in spec.PINS["bridges"]:
        query |= Q(entity_type=pin["entity_type"], legacy_pk=pin["legacy_pk"])
    rows = e.bounded(
        e.model("legacy_import.LegacyEntityMap").objects.filter(query, organization=org, source_system="myedu_mariadb"),
        cap=9,
    )
    fields = tuple(spec.PINS["bridges"][0])
    actual = [{k: r[k] for k in fields} for r in rows]

    def ordered(values):
        return sorted(values, key=lambda r: (r["entity_type"], r["legacy_pk"]))

    e.require(ordered(actual) == ordered(spec.PINS["bridges"]), "solmaz_typed_source_identity_changed")
    return rows


def protected_graph(raw, created):
    # Only these precise metadata columns may change. Every original body,
    # approval timestamp, assessment, grade, credit and hidden M2M row is hashed.
    changes = {
        "workload.TeachingTaskRow": {spec.ROW: set(spec.ROW_CHANGE)},
        "registrar.CourseOffering": {spec.COURSE: {"subject_id"}},
        "syllabus.Syllabus": {spec.SOURCE_SYLLABUS: {"current_version_id", "approved_version_id", "updated_at"}},
    }
    result = {}
    for label, rows in raw.items():
        pk = e.model(label)._meta.pk.attname
        clean = []
        for row in rows:
            ident = str(row[pk])
            if label == "workload.TeacherAssignment" and ident == spec.ASSIGNMENT:
                continue  # Exact excess15h allocation is retained in the audit/undo payload.
            if ident in created.get(label, []):
                continue
            omitted = changes.get(label, {}).get(ident, set())
            clean.append({k: v for k, v in row.items() if k not in omitted})
        if clean:
            result[label] = {"count": len(clean), "sha256": e.digest(clean)}
    return result


def snapshot(org, actor, *, created=None, corrected=False, archived=False):
    created = created or {}
    actor_scope(org, actor)
    e.require(reviewed_catalog_schema.fingerprints() == spec.PINS["schema"], "solmaz_unreviewed_relation_schema")
    schedule_lock.lock_schedule(org.pk, spec.PERIOD)
    period = e.model("organizations.AcademicPeriod").objects.select_for_update().get(pk=spec.PERIOD, organization=org)
    e.require(
        period.is_active
        and period.locked_at is None
        and period.academic_year == "2026/2027"
        and period.start_date <= timezone.localdate() <= period.end_date,
        "solmaz_current_period_changed",
    )
    e.require(
        e.model("auth.User").objects.filter(pk=spec.TEACHER, is_active=True).exists()
        and spec.TEACHER in eligible_instructor_user_ids(organization=org),
        "solmaz_teacher_permission_changed",
    )
    profile = e.bounded(e.model("accounts.UserProfile").objects.filter(user_id=spec.TEACHER), cap=1)
    e.require(
        len(profile) == 1
        and profile[0]["organization_id"] == spec.ORG
        and not profile[0]["is_deleted"]
        and profile[0]["deleted_at"] is None
        and profile[0]["blocked_at"] is None
        and profile[0]["access_state"] == "active",
        "solmaz_teacher_profile_changed",
    )
    task = (
        e.model("workload.TeachingTask").objects.select_for_update().get(pk=spec.PINS["task"]["id"], organization=org)
    )
    e.require(
        plan_reached_chair(task)
        and task.academic_year == "2026/2027"
        and str(task.chair_id) == spec.PINS["task"]["chair_id"],
        "solmaz_released_official_task_changed",
    )
    e.require(task.status == "amended", "solmaz_official_amendment_required")
    rows = e.bounded(
        e.model("workload.TeachingTaskRow").objects.filter(organization=org, pk__in=spec.PINS["rows"]), cap=4
    )
    row_pins = copy.deepcopy(spec.PINS["rows"])
    if corrected:
        row_pins[spec.ROW].update(spec.ROW_CHANGE)
    require_pins(rows, row_pins, "solmaz_exact_official_rows_changed")
    for row_id, group_id in spec.PINS["row_groups"].items():
        actual = set(
            map(
                str,
                e.model("workload.TeachingTaskRow")
                .objects.get(pk=row_id, organization=org)
                .groups.values_list("pk", flat=True),
            )
        )
        e.require(actual == {group_id}, "solmaz_exact_row_groups_changed")
    groups = e.bounded(
        e.model("organizations.OrgUnit").objects.filter(organization=org, pk__in=spec.PINS["groups"]), cap=4
    )
    require_pins(groups, spec.PINS["groups"], "solmaz_group_identity_changed")
    subjects = e.bounded(
        e.model("registrar.Subject").objects.filter(organization=org, pk__in=spec.PINS["subjects"]), cap=3
    )
    require_pins(subjects, spec.PINS["subjects"], "solmaz_subject_identity_changed")
    e.require(all(x["is_active"] for x in subjects), "solmaz_inactive_subject")
    assignments = e.bounded(
        e.model("workload.TeacherAssignment").objects.filter(organization=org, row_id__in=spec.PINS["rows"]), cap=7
    )
    assignment_pins = {a["id"]: copy.deepcopy(a) for a in spec.PINS["assignments"]}
    e.require(all(not a["groups_note"].strip() for a in assignments), "solmaz_unreviewed_group_allocation_note")
    if corrected:
        assignment_pins.pop(spec.ASSIGNMENT)
    require_pins(assignments, assignment_pins, "solmaz_exact_teacher_allocations_changed")
    excess = next((a for a in assignments if a["id"] == spec.ASSIGNMENT), None)
    if excess:
        closure = e.graph(spec.ORG, {"workload.TeacherAssignment": [spec.ASSIGNMENT]})
        e.require(
            set(closure) == {"workload.TeacherAssignment"} and len(closure["workload.TeacherAssignment"]) == 1,
            "solmaz_excess_allocation_has_dependent_records",
        )
    all_allocations = e.bounded(
        e.model("workload.TeacherAssignment").objects.filter(
            organization=org, teacher_id=spec.TEACHER, row__period_id=spec.PERIOD
        ),
        cap=7,
    )
    e.require(
        {a["id"] for a in all_allocations} == set(assignment_pins)
        and sum(a["hours"] for a in all_allocations) == (165 if corrected else 180),
        "solmaz_official_165_budget_changed",
    )
    courses = e.bounded(
        e.model("registrar.CourseOffering")._base_manager.filter(organization=org, pk__in=spec.PINS["courses"]), cap=4
    )
    course_pins = copy.deepcopy(spec.PINS["courses"])
    if corrected:
        course_pins[spec.COURSE]["subject_id"] = spec.CORRECT_SUBJECT
    require_pins(courses, course_pins, "solmaz_course_identity_changed")
    for course in courses:
        e.require(
            not e.model("registrar.CourseOffering")._base_manager.get(pk=course["id"]).is_intensive
            and e.model("registrar.CourseOffering")
            ._base_manager.filter(
                organization=org, group_id=course["group_id"], period_id=spec.PERIOD, subject_id=course["subject_id"]
            )
            .count()
            == 1,
            "solmaz_duplicate_or_intensive_course",
        )
    # The intended corrected destination must also be vacant before rebind.
    if not corrected:
        e.require(
            not e.model("registrar.CourseOffering")
            ._base_manager.filter(
                organization=org,
                group_id=course_pins[spec.COURSE]["group_id"],
                period_id=spec.PERIOD,
                subject_id=spec.CORRECT_SUBJECT,
            )
            .exists(),
            "solmaz_existing_canonical_course_requires_review",
        )
    syllabi = e.bounded(
        e.model("syllabus.Syllabus")._base_manager.filter(organization=org, offering_id__in=spec.PINS["courses"]), cap=2
    )
    syl_pins = copy.deepcopy(spec.PINS["syllabi"])
    if corrected or archived:
        syl_pins[spec.SOURCE_SYLLABUS].pop("approved_version_id")
        syl_pins[spec.SOURCE_SYLLABUS].pop("current_version_id")
    require_pins(syllabi, syl_pins, "solmaz_original_syllabi_changed")
    old_versions = e.bounded(
        e.model("syllabus.SyllabusVersion")
        ._base_manager.filter(organization=org, syllabus_id__in=spec.PINS["syllabi"])
        .exclude(pk__in=created.get("syllabus.SyllabusVersion", [])),
        cap=2,
    )
    require_pins(old_versions, spec.PINS["versions"], "solmaz_original_draft_or_approved_version_changed")
    donor = e.model("syllabus.SyllabusVersion")._base_manager.get(pk=spec.DONOR_VERSION, organization=org)
    e.require(
        content_fingerprints(section_data_map(donor))["canonical_body_sha256"] == spec.PINS["donor_body_sha256"],
        "solmaz_existing_own_donor_body_changed",
    )
    shares = e.bounded(
        e.model("syllabus.SyllabusShare")._base_manager.filter(
            Q(offering_id__in=spec.PINS["courses"]) | Q(syllabus_id__in=spec.PINS["syllabi"]), organization=org
        ),
        cap=2,
    )
    expected_shares = spec.SHARES if corrected else {}
    e.require(
        {r["offering_id"]: r["syllabus_id"] for r in shares} == expected_shares
        and all(r["source"] == "legacy" for r in shares),
        "solmaz_existing_share_or_human_target_requires_review",
    )
    if corrected:
        for course in courses:
            syllabus = syllabus_for_offering(
                organization=org,
                offering_id=course["id"],
                subject_id=course["subject_id"],
                period_id=spec.PERIOD,
                instructor_id=spec.TEACHER,
            )
            version = approved_version_for(syllabus)
            target = (
                spec.DONOR_VERSION
                if course["subject_id"] == spec.CORRECT_SUBJECT
                else created["syllabus.SyllabusVersion"][0]
            )
            e.require(version is not None and str(version.pk) == target, "solmaz_effective_approved_source_not_visible")
    raw = e.graph(
        spec.ORG,
        {
            "registrar.CourseOffering": spec.PINS["courses"],
            "workload.TeachingTaskRow": spec.PINS["rows"],
            "syllabus.Syllabus": spec.PINS["syllabi"],
        },
    )
    created_state = {}
    if created:
        e.require(
            set(created) == {"syllabus.SyllabusVersion", "syllabus.SyllabusSection", "syllabus.SyllabusShare"}
            and [
                len(created[k])
                for k in ("syllabus.SyllabusVersion", "syllabus.SyllabusSection", "syllabus.SyllabusShare")
            ]
            == [1, 10, 2],
            "solmaz_exact_created_scope_required",
        )
        imported = e.model("syllabus.SyllabusVersion")._base_manager.get(
            pk=created["syllabus.SyllabusVersion"][0], organization=org, syllabus_id=spec.SOURCE_SYLLABUS
        )
        e.require(
            imported.status == ("archived" if archived else "approved")
            and imported.approved_by_id is None
            and imported.approval_source == "migration"
            and imported.plan_hours == {"lecture": 30, "seminar": 30, "practical": 0, "lab": 0}
            and str(imported.applies_to_period_id) == spec.PERIOD
            and content_fingerprints(section_data_map(imported))["canonical_body_sha256"]
            == spec.PINS["source_canonical_body"],
            "solmaz_created_own_source_changed",
        )
        e.require(
            set(map(str, imported.sections.values_list("pk", flat=True))) == set(created["syllabus.SyllabusSection"]),
            "solmaz_complete_created_sections_changed",
        )
    for label, ids in created.items():
        found = e.bounded(e.model(label)._base_manager.filter(pk__in=ids), cap=10)
        e.require(all(row["organization_id"] == spec.ORG for row in found), "solmaz_created_tenant_changed")
        e.require(
            len(found) == len(ids) or (archived and label == "syllabus.SyllabusShare" and not found),
            "solmaz_created_record_missing",
        )
        created_state[label] = {"count": len(found), "sha256": e.digest(found)}
    enrollments = e.model("registrar.Enrollment")._base_manager.filter(
        organization=org, offering_id__in=spec.PINS["courses"]
    )
    credits = {str(k): v for k, v in credit_source.credits_for_enrollments(enrollments, organization=org).items()}
    memberships = e.bounded(
        e.model("organizations.Membership").objects.filter(organization=org, user_id=spec.TEACHER), cap=20
    )
    authority = {
        "roles": e.bounded(
            e.model("organizations.Role").objects.filter(organization=org, pk__in=[m["role_id"] for m in memberships]),
            cap=20,
        ),
        "profile": profile,
        "memberships": memberships,
        "bridges": bridges(org),
    }
    return {
        "corrected": corrected,
        "rows": {r["id"]: {k: r[k] for k in row_pins[r["id"]]} for r in rows},
        "courses": {r["id"]: {k: r[k] for k in course_pins[r["id"]]} for r in courses},
        "assignments": {r["id"]: {k: r[k] for k in assignment_pins[r["id"]]} for r in assignments},
        "protected": protected_graph(raw, created),
        "authority": e.digest(authority),
        "credits": e.digest(credits),
        "created": created,
        "created_state": created_state,
        "excess_allocation": excess,
        "pointers": {r["id"]: [r["current_version_id"], r["approved_version_id"]] for r in syllabi},
        "official_context": e.digest(
            [
                e.normal({k: getattr(task, k) for k in ("id", "academic_year", "status", "revision", "chair_id")}),
                groups,
                subjects,
            ]
        ),
    }
