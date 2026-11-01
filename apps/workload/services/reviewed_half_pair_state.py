"""Locked source/current scope and credit-aware previews for three compiled own classes."""

import datetime as dt
import json
from decimal import Decimal

from django.db.models import Q

from . import reviewed_half_pair_spec as spec
from .four_cell_recovery_history import validate_fixed_recovery_actor
from .group_projection import project_group_settings
from .repair_fingerprints import academic_queries, queryset_database_fingerprint
from .sbio235_state import RepairError, digest, model, records


def require(condition, code):
    if not condition:
        raise RepairError(code)


def bounded(query, *, lock=False, cap=5000):
    if lock:
        query = query.select_for_update()
    rows = list(query.order_by("pk").values()[: cap + 1])
    require(len(rows) <= cap, "half_pair_row_budget")
    return json.loads(json.dumps(rows, default=str))


def lock_scope(org):
    ids = [c["offering"]["id"] for c in spec.CASES]
    offering = model("registrar.CourseOffering")
    enrollment = model("registrar.Enrollment")
    subjects = {c["offering"]["subject_id"] for c in spec.CASES}
    periods = {c["offering"]["period_id"] for c in spec.CASES}
    students = enrollment.objects.filter(organization=org, offering_id__in=ids).values("student_id")
    family = enrollment.objects.filter(
        organization=org, student_id__in=students, offering__subject_id__in=subjects, offering__period_id__in=periods
    )
    family_ids = set(family.values_list("offering_id", flat=True))
    require(len(family_ids) <= 40 and family.count() <= 500, "half_pair_lock_scope_budget")
    list(offering.objects.filter(organization=org, pk__in=family_ids | set(ids)).order_by("pk").select_for_update())
    list(family.order_by("pk").select_for_update())


def historical_scope(org, *, lock):
    if not any(c.get("authority") == "historical_own_class_only_no_current_assignment" for c in spec.CASES):
        return {}
    pin = spec.HISTORICAL_ROW
    row = model("workload.TeachingTaskRow").objects.filter(organization=org, pk=pin["id"])
    require(row.count() == 1, "half_pair_historical_row_missing")
    obj = row.first()
    require(
        all(str(getattr(obj, key)) == str(value) for key, value in pin["fields"].items()),
        "half_pair_historical_zero_allocation_row_changed",
    )
    assignments = model("workload.TeacherAssignment").objects.filter(organization=org, row_id=pin["id"])
    require(not assignments.exists(), "half_pair_historical_allocation_graph_changed")
    require(
        set(str(pk) for pk in obj.groups.values_list("pk", flat=True)) == {pin["group_id"]},
        "half_pair_historical_group_geometry_changed",
    )
    group_query = model("organizations.OrgUnit").objects.filter(organization=org, pk=spec.HISTORICAL_GROUP["id"])
    require(group_query.count() == 1, "half_pair_historical_group_missing")
    group = group_query.first()
    for key in ("id", "parent_id", "is_active", "unit_type"):
        require(
            str(getattr(group, key)) == str(spec.HISTORICAL_GROUP[key]), "half_pair_historical_group_identity_changed"
        )
    tenant_groups = model("organizations.OrgUnit").objects.filter(organization=org)
    require(tenant_groups.count() <= 5000, "half_pair_group_identity_budget")
    require(
        project_group_settings(group.settings, canonical_group_ids=tenant_groups.values_list("pk", flat=True))
        == spec.HISTORICAL_GROUP["settings"],
        "half_pair_historical_group_geometry_changed",
    )
    bridge = model("legacy_import.LegacyEntityMap")
    scope = Q(pk__in=[])
    for pinrow in spec.HISTORICAL_BRIDGE:
        scope |= Q(
            entity_type=pinrow["entity_type"], legacy_pk=pinrow["legacy_pk"], source_system=pinrow["source_system"]
        )
    bridge_query = bridge.objects.filter(scope, organization=org)
    rows = bounded(bridge_query, lock=lock, cap=8)
    actual = {r["id"]: r for r in rows}
    require(set(actual) == {r["id"] for r in spec.HISTORICAL_BRIDGE}, "half_pair_historical_dimension_bridge_conflict")
    for expected in spec.HISTORICAL_BRIDGE:
        require(
            all(str(actual[expected["id"]][key]) == str(value) for key, value in expected.items()),
            "half_pair_historical_dimension_bridge_changed",
        )
    through = row.first().groups.through.objects.filter(teachingtaskrow_id=obj.pk)
    for query in (row, assignments, through, group_query):
        bounded(query, lock=lock, cap=50)
    return {
        "row": queryset_database_fingerprint(row),
        "assignments": queryset_database_fingerprint(assignments),
        "row_groups": queryset_database_fingerprint(through),
        "dimension_bridge": {"count": len(rows), "sha256": digest(rows)},
        "group": queryset_database_fingerprint(group_query),
    }


def mark_pin(row):
    return (
        str(row[0]),
        str(row[1]),
        row[2],
        format(Decimal(str(row[3])).normalize(), "f") if row[3] is not None else None,
        row[4],
    )


def validate_actor(org, actor, *, lock=False):
    validate_fixed_recovery_actor(actor=actor, organization=org)
    profile = model("accounts.UserProfile").objects.filter(
        user=actor,
        access_state="active",
        is_deleted=False,
        deleted_at__isnull=True,
        deleted_by__isnull=True,
        blocked_at__isnull=True,
        blocked_by__isnull=True,
    )
    if lock:
        profile = profile.select_for_update()
    require(profile.exists(), "half_pair_active_actor_profile_required")


def capture(org, actor, *, hours, lock=False, correction_ids=()):
    validate_actor(org, actor, lock=lock)
    ids = [c["offering"]["id"] for c in spec.CASES]
    courses = model("registrar.CourseOffering").objects.filter(organization=org, pk__in=ids).order_by("pk")
    if lock:
        list(courses.select_for_update())
    offerings = list(courses)
    require(len(offerings) == len(spec.CASES), "half_pair_fixed_courses_missing")
    for case in spec.CASES:
        course = next(o for o in offerings if str(o.pk) == case["offering"]["id"])
        for key, value in case["offering"].items():
            actual = getattr(course, key)
            require(str(actual) == str(value), "half_pair_current_course_identity_changed")
    row = model("workload.TeachingTaskRow").objects.filter(organization=org, pk=spec.ROW)
    require(row.count() == 1, "half_pair_official_row_missing")
    assignments = model("workload.TeacherAssignment").objects.filter(organization=org, row_id=spec.ROW)
    require(
        {
            str(r[0]): tuple(r[1:])
            for r in assignments.values_list("id", "teacher_id", "activity", "hours", "is_hourly_paid")
        }
        == spec.ASSIGNMENTS,
        "half_pair_official_assignment_changed",
    )
    require(
        set(str(pk) for pk in row.first().groups.values_list("pk", flat=True)) == set(spec.ALLOCATION_GROUPS),
        "half_pair_official_group_geometry_changed",
    )
    require(
        model("registrar.AssessmentScheme").objects.filter(organization=org, offering_id__in=ids).count() == len(ids),
        "half_pair_existing_scheme_required_no_incidental_creation",
    )
    audit_query = model("audit.AuditLog").objects.filter(
        organization=org, resource_id__in=[*ids, *[c["lesson"]["id"] for c in spec.CASES]]
    )
    audit_rows = bounded(audit_query, cap=1000)
    for record in audit_rows:
        changes = record.get("changes") or []
        require(isinstance(changes, (list, dict)), "half_pair_unresolved_grade_audit")
        hours_keys = {"hours", "old_hours", "new_hours"}
        if isinstance(changes, dict):
            require(not hours_keys.intersection(changes), "half_pair_prior_direct_hours_edit_requires_review")
            changes = []
        for values in (record.get("old_values"), record.get("new_values")):
            if isinstance(values, dict):
                require(not hours_keys.intersection(values), "half_pair_prior_direct_hours_edit_requires_review")
        for change in changes:
            if not isinstance(change, dict):
                continue
            item = change.get("item", "")
            if isinstance(item, str) and any(c["lesson"]["date"] in item for c in spec.CASES) and "dərs saat" in item:
                require(False, "half_pair_prior_direct_hours_edit_requires_review")
    lessons = []
    touched = set()
    fixed_absent_cells = 0
    for case in spec.CASES:
        query = model("registrar.Lesson").objects.filter(organization=org, pk=case["lesson"]["id"])
        if lock:
            query = query.select_for_update()
        lesson = query.get()
        for key, value in case["lesson"].items():
            actual = getattr(lesson, key)
            if isinstance(actual, (dt.date, dt.time)):
                actual = actual.isoformat()
            require(str(actual) == str(value), "half_pair_current_lesson_identity_changed")
        require(lesson.hours == hours, "half_pair_hours_changed")
        marks = model("registrar.LessonMark").objects.filter(organization=org, lesson=lesson)
        actual = {mark_pin(r) for r in marks.values_list("id", "enrollment_id", "status", "score", "entered_by_id")}
        if "marks_sha256" in case:
            require(
                len(actual) == case["mark_count"] and digest(sorted(actual)) == case["marks_sha256"],
                "half_pair_source_proven_marks_changed",
            )
        else:
            require(actual == {mark_pin(r) for r in case["marks"]}, "half_pair_source_proven_marks_changed")
        fixed_absent_cells += sum(r[2] == "absent" for r in actual)
        touched.update(r[1] for r in actual)
        corrections = model("registrar.LessonCorrection").objects.filter(organization=org, lesson=lesson)
        require(
            not corrections.exclude(pk__in=correction_ids).exists(),
            "half_pair_existing_lesson_correction_requires_review",
        )
        bounded(marks, lock=lock)
        lessons.append(lesson)
    enr = model("registrar.Enrollment")
    own = enr.objects.filter(organization=org, pk__in=touched)
    require(own.count() == len(touched), "half_pair_mark_enrollment_tenant_conflict")
    # Same-period/subject family includes inactive/dropped/header and both graph directions.
    students = own.values_list("student_id", flat=True)
    pairs = Q(pk__in=[])
    for course in offerings:
        pairs |= Q(offering__subject_id=course.subject_id, offering__period_id=course.period_id)
    family_query = enr.objects.filter(pairs, organization=org, student_id__in=students)
    family = bounded(family_query, lock=lock, cap=500)
    by_id = {r["id"]: r for r in family}
    family_courses = list(
        model("registrar.CourseOffering").objects.filter(organization=org, pk__in={r["offering_id"] for r in family})
    )
    require(len(family_courses) <= 40, "half_pair_course_family_budget")
    family_marks = model("registrar.LessonMark").objects.filter(organization=org, enrollment_id__in=by_id)
    mark_rows = bounded(family_marks, lock=lock)
    credit_query = model("registrar.AbsenceCredit").objects.filter(organization=org, enrollment_id__in=by_id)
    credit_rows = bounded(credit_query, lock=lock, cap=500)
    correction_query = model("registrar.LessonCorrection").objects.filter(organization=org, pk__in=correction_ids)
    reversal_query = model("registrar.CorrectionReversal").objects.filter(
        organization=org, lesson_correction_id__in=correction_ids
    )
    correction_fingerprint = digest(bounded(correction_query, lock=lock, cap=len(spec.CASES)))
    reversal_fingerprint = digest(bounded(reversal_query, lock=lock, cap=len(spec.CASES)))
    credits_by_id = {r["id"]: r for r in credit_rows}
    reversed_ids = set()
    for credit in credit_rows:
        root_id = credit["reverses_id"]
        if root_id:
            root = credits_by_id.get(root_id)
            require(
                root is not None
                and root["reverses_id"] is None
                and root["enrollment_id"] == credit["enrollment_id"]
                and root["hours"] == credit["hours"]
                and root_id not in reversed_ids,
                "half_pair_credit_reversal_scope_changed",
            )
            reversed_ids.add(root_id)
    require(
        not model("registrar.AbsenceCredit")
        .objects.filter(reverses_id__in=credits_by_id)
        .exclude(pk__in=credits_by_id)
        .exists(),
        "half_pair_credit_reverse_closure_incomplete",
    )
    active = {}
    for credit in credit_rows:
        if not credit["reverses_id"] and credit["id"] not in reversed_ids:
            active[credit["enrollment_id"]] = active.get(credit["enrollment_id"], 0) + credit["hours"]
    # Protect every raw field, not only status/value. Exclude only sanctioned hour/cache fields.
    protected = {"historical_authority_no_rights_granted": historical_scope(org, lock=lock)}
    for name, query in academic_queries(organization_id=org.pk, offerings=family_courses).items():
        if name == "lesson":
            query = query.exclude(pk__in=[lesson.pk for lesson in lessons])
        if name == "enrollment":
            query = query.values(*[f.attname for f in enr._meta.concrete_fields if f.name != "absence_hours"])
        # One bounded SQL probe also fingerprints the complete accepted set.
        # cap+1 is rejected, never presented as a truncated full fingerprint.
        probe = query.order_by("pk").values("pk")[:50001]
        fingerprint = queryset_database_fingerprint(query.filter(pk__in=probe))
        require(fingerprint["count"] <= 50000, "half_pair_protected_row_budget")
        protected[name] = fingerprint
    for name, query in {"credits": credit_query, "row": row, "assignments": assignments}.items():
        protected[name] = queryset_database_fingerprint(query)
    journal_corrections = model("registrar.JournalCorrection").objects.filter(
        organization=org, enrollment_ref__in=by_id
    )
    other_lesson_corrections = (
        model("registrar.LessonCorrection")
        .objects.filter(organization=org, lesson__offering_id__in=[o.pk for o in family_courses])
        .exclude(lesson_id__in=[lesson.pk for lesson in lessons])
    )
    formal_reversals = (
        model("registrar.CorrectionReversal")
        .objects.filter(organization=org)
        .filter(Q(journal_correction__in=journal_corrections) | Q(lesson_correction__in=other_lesson_corrections))
    )
    for name, query in {
        "journal_corrections": journal_corrections,
        "other_lesson_corrections": other_lesson_corrections,
        "formal_reversals": formal_reversals,
    }.items():
        bounded(query, lock=lock, cap=500)
        protected[name] = queryset_database_fingerprint(query)
    protected["untouched_caches"] = queryset_database_fingerprint(
        enr.objects.filter(organization=org, offering_id__in=[o.pk for o in family_courses])
        .exclude(pk__in=by_id)
        .values("id", "absence_hours")
    )
    protected["target_lessons"] = digest(
        [
            {k: v for k, v in r.items() if k != "hours"}
            for r in records(model("registrar.Lesson").objects.filter(pk__in=[lesson.pk for lesson in lessons]))
        ]
    )
    # Derive actual raw sums, never predecessor cache. All existing i/e/credits remain untouched.
    lesson_hours = dict(
        model("registrar.Lesson")
        .objects.filter(organization=org, pk__in={r["lesson_id"] for r in mark_rows})
        .values_list("pk", "hours")
    )
    own_hours, own_count = {}, {}
    changes = {str(lesson.pk): 1 - lesson.hours for lesson in lessons}
    additions = {}
    for mark in mark_rows:
        if mark["status"] != "absent":
            continue
        eid = mark["enrollment_id"]
        own_hours[eid] = (
            own_hours.get(eid, 0) + lesson_hours[next(pk for pk in lesson_hours if str(pk) == mark["lesson_id"])]
        )
        own_count[eid] = own_count.get(eid, 0) + 1
        additions[eid] = additions.get(eid, 0) + changes.get(mark["lesson_id"], 0)
    courses_by_id = {str(o.pk): o for o in family_courses}
    predecessors = {}
    for r in family:
        target = by_id.get(r["superseded_by_id"])
        if r["status"] != "dropped" or not target:
            continue
        a, b = courses_by_id[r["offering_id"]], courses_by_id[target["offering_id"]]
        require(
            r["student_id"] == target["student_id"]
            and a.subject_id == b.subject_id
            and a.period_id == b.period_id
            and r["id"] != target["id"],
            "half_pair_supersession_identity_conflict",
        )
        predecessors.setdefault(target["id"], []).append(r["id"])
    affected = set(touched)
    pending = set(touched)
    while pending:
        nxt = {
            by_id[e]["superseded_by_id"]
            for e in pending
            if by_id[e]["superseded_by_id"] in by_id and by_id[e]["status"] == "dropped"
        } - affected
        affected |= nxt
        pending = nxt
    preview = []
    for eid, r in by_id.items():

        def derived(after, eid=eid):
            raw = own_hours.get(eid, 0) + (additions.get(eid, 0) if after else 0)
            carry = sum(
                max(0, own_hours.get(p, 0) + (additions.get(p, 0) if after else 0) - active.get(p, 0))
                for p in predecessors.get(eid, [])
            )
            return max(0, raw + carry - active.get(eid, 0))

        preview.append(
            {
                "enrollment_id": eid,
                "touched": eid in affected,
                "before_cached": r["absence_hours"],
                "before_derived": derived(False),
                "after_derived": derived(True),
                "raw_qb_count": own_count.get(eid, 0),
            }
        )
    return {
        "fixed_absent_cells": fixed_absent_cells,
        "available_grade_audits": digest(audit_rows),
        "corrections": correction_fingerprint,
        "reversals": reversal_fingerprint,
        "protected": protected,
        "preview": sorted(preview, key=lambda r: r["enrollment_id"]),
        "credits": digest(credit_rows),
        "hours": hours,
    }, lessons
