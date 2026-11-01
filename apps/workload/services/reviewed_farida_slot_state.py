"""Fresh fixed-slot control; unrelated academic values are preserved per write, not frozen."""

import hashlib
import json

from django.db.models import Q

from . import reviewed_farida_slot_spec as spec
from .group_projection import project_group_settings
from .repair_fingerprints import academic_queries, queryset_database_fingerprint
from .reviewed_half_pair_state import bounded, require, validate_actor
from .sbio235_state import model

PARK_FIELDS = {"is_parked", "parked_at", "parked_by_id", "park_reason", "updated_at"}


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def capture(org, actor, *, lock=False, known_mutations=()):
    validate_actor(org, actor, lock=lock)
    courses = model("registrar.CourseOffering").objects.filter(organization=org, pk__in=spec.OFFERINGS).order_by("pk")
    if lock:
        courses = courses.select_for_update(nowait=True)
    offerings = list(courses)
    require(len(offerings) == len(spec.OFFERINGS), "farida_slot_fixed_courses_missing")
    for course in offerings:
        expected = spec.OFFERINGS[str(course.pk)]
        require(
            all(str(getattr(course, key)) == str(value) for key, value in expected.items()),
            "farida_slot_course_identity_changed",
        )
    period = model("organizations.AcademicPeriod").objects.get(organization=org, pk=spec.PERIOD)
    require(
        period.is_active and period.locked_at is None and period.academic_year == "2026/2027",
        "farida_slot_current_period_locked_or_changed",
    )
    groups = model("organizations.OrgUnit").objects.filter(organization=org, pk__in=spec.GROUPS)
    group_rows = bounded(groups, lock=lock, cap=8)
    require(len(group_rows) == len(spec.GROUPS), "farida_slot_group_scope_changed")
    for group in group_rows:
        expected = spec.GROUPS[group["id"]]
        require(
            all(str(group[key]) == str(expected[key]) for key in ("parent_id", "unit_type", "is_active")),
            "farida_slot_group_identity_changed",
        )
        projected = project_group_settings(group["settings"], canonical_group_ids=spec.GROUP_FAMILY)
        require(projected == expected["settings"], "farida_slot_sector_or_parent_geometry_changed")
    group_family = (
        model("organizations.OrgUnit")
        .objects.filter(organization=org, unit_type="group")
        .filter(
            Q(pk__in=spec.GROUP_FAMILY)
            | Q(settings__parent_group__in=spec.GROUP_FAMILY)
            | Q(settings__canonical_group__in=spec.GROUP_FAMILY)
        )
    )
    require(
        set(map(str, group_family.values_list("pk", flat=True))) == set(spec.GROUP_FAMILY),
        "farida_slot_new_group_alias_requires_review",
    )
    row_model = model("workload.TeachingTaskRow")
    scope = row_model.objects.filter(organization=org, subject_id=spec.SUBJECT, groups__in=group_family).filter(
        Q(period_id=spec.PERIOD) | Q(period__isnull=True, season="fall", task__academic_year="2026/2027")
    )
    ids = set(map(str, scope.values_list("pk", flat=True)))
    require(ids == set(spec.AUTHORITY_ROWS), "farida_slot_new_intersecting_workload_requires_review")
    rows = row_model.objects.filter(organization=org, pk__in=ids)
    row_records = bounded(rows, lock=lock, cap=8)
    row = next(r for r in row_records if r["id"] == spec.ROW)
    require(all(str(row[k]) == str(v) for k, v in spec.ROW_FIELDS.items()), "farida_slot_official_positive_row_changed")
    row_groups = rows.get(pk=spec.ROW).groups
    require(
        set(map(str, row_groups.values_list("pk", flat=True))) == set(spec.AZ_GROUPS),
        "farida_slot_official_group_scope_changed",
    )
    assignments = model("workload.TeacherAssignment").objects.filter(organization=org, row_id__in=ids)
    assignment_records = bounded(assignments, lock=lock, cap=16)
    require(
        {r["id"]: (r["teacher_id"], r["activity"], r["hours"], r["is_hourly_paid"]) for r in assignment_records}
        == spec.ASSIGNMENTS,
        "farida_slot_assignment_graph_changed",
    )
    require(
        all(not (r.get("groups_note") or "").strip() for r in assignment_records),
        "farida_slot_partial_assignment_requires_review",
    )
    require(
        not model("registrar.TeachingHandover")
        .objects.filter(organization=org, offering_id__in=spec.OFFERINGS)
        .exists(),
        "farida_slot_handover_authority_requires_review",
    )
    require(
        not model("registrar.JournalShare").objects.filter(organization=org, offering_id__in=spec.OFFERINGS).exists(),
        "farida_slot_additional_share_authority_requires_review",
    )
    Slot = model("registrar.ScheduleSlot")
    slots = bounded(Slot.all_objects.filter(organization=org, offering_id__in=spec.OFFERINGS), lock=lock, cap=16)
    require({r["id"] for r in slots} == set(spec.SLOTS), "farida_slot_six_row_scope_changed")
    for slot in slots:
        expected = spec.SLOTS[slot["id"]]["geometry"]
        require(
            all(str(slot[k]) == str(v) for k, v in expected.items() if k != "is_parked" or slot["id"] != spec.TARGET),
            "farida_slot_geometry_changed",
        )
    expected_audits = bounded(
        model("audit.AuditLog").objects.filter(organization=org, pk__in=spec.CREATION_AUDITS), lock=lock, cap=2
    )
    require({r["id"] for r in expected_audits} == set(spec.CREATION_AUDITS), "farida_slot_creation_audit_missing")
    for audit in expected_audits:
        pin = spec.CREATION_AUDITS[audit["id"]]
        require(canonical(audit) == pin["sha256"], "farida_slot_creation_audit_changed")
    docx = next(r for r in expected_audits if r["id"] == spec.DOCX_AUDIT)
    inference = next(r for r in expected_audits if r["id"] == spec.INFERENCE_AUDIT)
    require(
        spec.TARGET in inference["new_values"].get("created_ids", [])
        and spec.TARGET not in docx["new_values"].get("created_ids", []),
        "farida_slot_inference_origin_not_exact",
    )
    require(
        set(spec.SLOTS) - {spec.TARGET} <= set(docx["new_values"].get("created_ids", [])),
        "farida_slot_original_docx_ids_changed",
    )
    # Only scheduling-domain mutations and explicit fixed-slot resources matter here.
    # Grade-value/syllabus/credit audit writes are intentionally outside this control baseline.
    audit_query = (
        model("audit.AuditLog")
        .objects.filter(organization=org)
        .exclude(resource_type=spec.RESOURCE)
        .exclude(resource_type__startswith="registrar.grade.")
    )
    direct = Q(resource_id__in=spec.SLOTS)
    for pk in spec.SLOTS:
        direct |= (
            Q(old_values__id=pk)
            | Q(new_values__id=pk)
            | Q(new_values__restored_alias_slot=pk)
            | Q(new_values__replaces_slot_id=pk)
        )
        for field in ("created_ids", "created_slot_ids", "removed_ids", "parked_ids", "slot_ids"):
            direct |= Q(**{"new_values__" + field + "__contains": [pk]})
    other_audits = bounded(
        audit_query.filter(direct).exclude(pk__in=[*spec.CREATION_AUDITS, *known_mutations]).exclude(action="view"),
        lock=lock,
        cap=100,
    )
    require(not other_audits, "farida_slot_later_scheduling_override_requires_review")
    target = next(r for r in slots if r["id"] == spec.TARGET)
    overlaps = (
        Slot.objects.filter(
            organization=org,
            offering__period_id=spec.PERIOD,
            is_parked=False,
            weekday=target["weekday"],
            start_time__lt=target["end_time"],
            end_time__gt=target["start_time"],
        )
        .exclude(pk=spec.TARGET)
        .filter(
            Q(offering__group_id=spec.OFFERINGS[target["offering_id"]]["group_id"])
            | Q(instructor_id=spec.TEACHER)
            | Q(instructor__isnull=True, offering__instructor_id=spec.TEACHER)
            | Q(room__iexact=target["room"])
        )
    )
    conflict_rows = bounded(overlaps, lock=lock, cap=100)
    lesson_query = model("registrar.Lesson").objects.filter(
        organization=org,
        offering_id=target["offering_id"],
        kind=target["kind"],
        start_time=target["start_time"],
        date__iso_week_day=target["weekday"],
    )
    linked = bounded(lesson_query, lock=lock, cap=50)
    require({r["id"] for r in linked} == set(spec.LINKED_LESSONS), "farida_slot_new_linked_lesson_requires_review")
    linked_topology = [
        {k: v for k, v in r.items() if k not in {"hours", "updated_at", "topic", "syllabus_week"}} for r in linked
    ]
    linked_marks = list(
        model("registrar.LessonMark")
        .objects.filter(organization=org, lesson_id__in=spec.LINKED_LESSONS)
        .order_by("pk")
        .values("id", "lesson_id", "enrollment_id")
    )
    require(len(linked_marks) <= 100, "farida_slot_linked_mark_budget")
    require(
        sorted((str(r["id"]), str(r["lesson_id"]), str(r["enrollment_id"])) for r in linked_marks)
        == spec.LINKED_MARK_REFS,
        "farida_slot_new_linked_mark_reference_requires_review",
    )
    maps = model("legacy_import.LegacyEntityMap").objects.filter(
        organization=org, target_model_label__iexact="registrar.scheduleslot", target_pk__in=spec.SLOTS
    )
    require(not maps.exists(), "farida_slot_new_immutable_mapping_requires_review")
    reverse_refs = {}
    for relation in Slot._meta.related_objects:
        if relation.many_to_many:
            require(False, "farida_slot_unknown_many_to_many_reference")
        query = relation.related_model._base_manager.filter(**{relation.field.attname: spec.TARGET})
        require(not query.exists(), "farida_slot_new_reverse_reference_requires_review")
        reverse_refs[relation.related_model._meta.label + "." + relation.field.name] = 0
    through = rows.get(pk=spec.ROW).groups.through.objects.filter(teachingtaskrow_id__in=ids)
    return {
        "slots": slots,
        "creation_audits": {r["id"]: canonical(r) for r in expected_audits},
        "courses": canonical(bounded(courses, lock=False, cap=3)),
        "period": canonical({f.attname: getattr(period, f.attname) for f in period._meta.concrete_fields}),
        "groups": canonical(group_rows),
        "rows": canonical(row_records),
        "row_groups": canonical(bounded(through, lock=lock, cap=16)),
        "assignments": canonical(assignment_records),
        "conflicts": canonical(conflict_rows),
        "linked_topology": canonical(linked_topology),
        "linked_marks": canonical(linked_marks),
        "reverse_refs": reverse_refs,
    }, offerings


def academic(org, offerings):
    result = {}
    for label, query in academic_queries(organization_id=org.pk, offerings=offerings).items():
        if label == "scheduleslot":
            continue
        probe = query.order_by("pk").values("pk")[:50001]
        value = queryset_database_fingerprint(query.filter(pk__in=probe))
        require(value["count"] <= 50000, "farida_slot_academic_preservation_budget")
        result[label] = value
    enrs = model("registrar.Enrollment").objects.filter(organization=org, offering__in=offerings)
    credits = model("registrar.AbsenceCredit").objects.filter(organization=org, enrollment__in=enrs)
    result["absence_credit"] = canonical(bounded(credits, cap=1000))
    return result
