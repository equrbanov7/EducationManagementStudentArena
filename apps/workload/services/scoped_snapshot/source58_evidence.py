"""Closed Source58 SELECT-only evidence; deliberately unregistered and never a writer."""

from collections import Counter

from django.db.models import Q

from apps.registrar.public import absence_counter_preview

from ..offering_sync import eligible_instructor_ids
from ..reviewed_leyla_catalog_graph import digest, model
from . import source58_evidence_spec as fixed
from .source58_evidence_history import collect_history
from .source58_evidence_rows import MAX_DEPTH, EvidenceLimit, Rows, budget, export_budget, project, require_readonly


def _closure(reader, label, initial, link):
    cls = model(label)
    rows, pending, expanded = {}, set(map(str, initial)), set()
    for _depth in range(MAX_DEPTH):
        if not pending:
            break
        values = reader.read(cls._base_manager.filter(Q(pk__in=pending) | Q(**{link + "__in": pending})), cap=1000)
        for row in values:
            rows[str(row["id"])] = row
        expanded.update(pending)
        following = {str(row[link]) for row in values if row[link] is not None}
        following |= {str(row["id"]) for row in values}
        pending = following - expanded
    if pending:
        raise EvidenceLimit("source58_" + label.split(".")[-1].lower() + "_closure_depth")
    for key in rows:
        path, current = set(), key
        while current in rows:
            if current in path:
                raise EvidenceLimit("source58_reference_cycle")
            path.add(current)
            following = rows[current][link]
            if following is None:
                break
            current = str(following)
            if current not in rows:
                raise EvidenceLimit("source58_dangling_reference")
    return rows


def _family(reader):
    query = Q(pk__in=fixed.OFFERINGS)
    for pin in fixed.OFFERINGS.values():
        query |= Q(subject_id=pin["subject_id"], period_id=pin["period_id"])
    return reader.read(
        model("registrar.CourseOffering")._base_manager.filter(query, organization_id=fixed.ORG), cap=200
    )


def _extra_evidence(reader, enrollments, lessons):
    enrs, students = set(enrollments), {row["student_id"] for row in enrollments.values()}
    source = Q(
        source_system="myedu_mariadb",
        source_table__in=("journals_dates_points", "journals_dates_points_archive"),
        source_pk__in=fixed.CASES,
    )
    queries = {
        "registrar.JournalCorrection": model("registrar.JournalCorrection")
        ._base_manager.filter(organization_id=fixed.ORG)
        .filter(Q(enrollment_ref__in=enrs) | Q(lesson_ref__in=lessons)),
        "registrar.LessonCorrection": model("registrar.LessonCorrection")
        ._base_manager.filter(organization_id=fixed.ORG)
        .filter(Q(lesson_id__in=lessons) | Q(lesson_id__isnull=True)),
        "registrar.LegacyExcuseDocument": model("registrar.LegacyExcuseDocument")
        ._base_manager.filter(organization_id=fixed.ORG)
        .filter(Q(student_id__in=students) | Q(student_id__isnull=True)),
        "registrar.LegacyGradeFact": model("registrar.LegacyGradeFact")
        ._base_manager.filter(organization_id=fixed.ORG)
        .filter(source | Q(enrollment_id__in=enrs)),
        "registrar.LegacyGradeArtifact": model("registrar.LegacyGradeArtifact")._base_manager.filter(
            source, organization_id=fixed.ORG
        ),
    }
    return {label: reader.read(query, cap=1000) for label, query in queries.items()}


def _ledger(reader):
    query = Q(pk__in=[])
    for entity, keys in fixed.HISTORY_SCOPE.source_keys.items():
        query |= Q(entity_type=entity, legacy_pk__in=keys)
    rows = reader.read(
        model("legacy_import.LegacyEntityMap")._base_manager.filter(
            query, organization_id=fixed.ORG, source_system="myedu_mariadb"
        ),
        cap=1000,
    )
    found = {(row["entity_type"], row["legacy_pk"]) for row in rows}
    missing = [
        {"entity_type": entity, "legacy_pk": key}
        for entity, keys in fixed.HISTORY_SCOPE.source_keys.items()
        for key in keys
        if (entity, key) not in found
    ]
    return rows, missing


def _claims(academic, offering_map):
    lessons = {row["id"]: row for row in academic.get("registrar.Lesson", [])}
    enrollments = {row["id"]: row for row in academic.get("registrar.Enrollment", [])}
    output = []
    for point, case in fixed.CASES.items():
        pin = fixed.OFFERINGS[case["offering_id"]]
        matches = []
        for mark in academic.get("registrar.LessonMark", []):
            lesson, enrollment = lessons.get(mark["lesson_id"]), enrollments.get(mark["enrollment_id"])
            if not lesson or not enrollment:
                raise EvidenceLimit("source58_mark_forward_reference_missing")
            offering = offering_map.get(lesson["offering_id"])
            if (
                offering
                and enrollment["student_id"] == case["student_id"]
                and lesson["date"] == case["date"]
                and offering["subject_id"] == pin["subject_id"]
                and offering["period_id"] == pin["period_id"]
            ):
                matches.append(
                    {
                        "mark_id": mark["id"],
                        "lesson_id": lesson["id"],
                        "enrollment_id": enrollment["id"],
                        "offering_id": lesson["offering_id"],
                        "status": mark["status"],
                        "enrollment_status": enrollment["status"],
                        "kind": lesson["kind"],
                        "start_time": lesson["start_time"],
                        "exact_source_slot": lesson["kind"] == case["kind"]
                        and lesson["start_time"] == case["start_time"],
                        "protected_row_sha256": mark["_raw_sha"],
                    }
                )
        output.append(
            {"source_point_id": point, "target_enrollment_id": case["enrollment_id"], "existing_claims": matches}
        )
    return output


def _capture():
    actor = require_readonly()
    reader = Rows()
    offerings = _family(reader)
    family_ids = {row["id"] for row in offerings}
    initial = reader.read(model("registrar.Enrollment")._base_manager.filter(offering_id__in=family_ids), cap=1000)
    target_ids = {case["enrollment_id"] for case in fixed.CASES.values()}
    enrollments = _closure(
        reader, "registrar.Enrollment", {row["id"] for row in initial} | target_ids, "superseded_by_id"
    )
    credits = {}
    for _depth in range(MAX_DEPTH):
        current = reader.read(
            model("registrar.AbsenceCredit")._base_manager.filter(enrollment_id__in=enrollments), cap=1000
        )
        credits = _closure(reader, "registrar.AbsenceCredit", {row["id"] for row in current}, "reverses_id")
        extra_enrollments = {row["enrollment_id"] for row in credits.values()} - enrollments.keys()
        if not extra_enrollments:
            break
        enrollments = _closure(reader, "registrar.Enrollment", set(enrollments) | extra_enrollments, "superseded_by_id")
    else:
        raise EvidenceLimit("source58_credit_enrollment_closure_depth")
    all_offering_ids = family_ids | {row["offering_id"] for row in enrollments.values()}
    offerings = reader.read(model("registrar.CourseOffering")._base_manager.filter(pk__in=all_offering_ids), cap=500)
    offering_map = {row["id"]: row for row in offerings}
    lessons = reader.read(model("registrar.Lesson")._base_manager.filter(offering_id__in=all_offering_ids), cap=5000)
    extra = _extra_evidence(reader, enrollments, {row["id"] for row in lessons})
    allocations = reader.read(
        model("workload.TeachingTaskRow")
        ._base_manager.filter(organization_id=fixed.ORG)
        .filter(
            Q(pk__in=[])
            | Q(
                subject_id__in={row["subject_id"] for row in offerings},
                period_id__in={row["period_id"] for row in offerings},
            )
        ),
        cap=1000,
    )
    roots = {
        "registrar.CourseOffering": all_offering_ids,
        "registrar.Enrollment": set(enrollments),
        "registrar.AbsenceCredit": set(credits),
        "workload.TeachingTaskRow": {row["id"] for row in allocations},
    }
    roots.update({label: {row["id"] for row in rows} for label, rows in extra.items()})
    academic = reader.graph(roots)
    claims = _claims(academic, offering_map)
    source = Counter()
    for case in fixed.CASES.values():
        source[case["enrollment_id"]] += case["hours"]
    missing_targets = sorted(target_ids - enrollments.keys())
    previews = absence_counter_preview(
        organization_id=fixed.ORG,
        added_hours_by_enrollment={key: value for key, value in source.items() if key in enrollments},
    )
    claimed = {row["target_enrollment_id"] for row in claims if row["existing_claims"]}
    for row in previews:
        row["current_claim_requires_review"] = row["enrollment_id"] in claimed
        row["source_effect_is_conditional_on_missing_cells"] = True
    ledger, missing_maps = _ledger(reader)
    teachers = {row["instructor_id"] for row in offerings if row["instructor_id"] is not None}
    users = teachers | {row["student_id"] for row in enrollments.values()}
    context = {
        "auth.User": reader.read(model("auth.User")._base_manager.filter(pk__in=users), cap=1500),
        "accounts.UserProfile": reader.read(
            model("accounts.UserProfile")._base_manager.filter(organization_id=fixed.ORG, user_id__in=users), cap=1500
        ),
        "organizations.Membership": reader.read(
            model("organizations.Membership")._base_manager.filter(organization_id=fixed.ORG, user_id__in=teachers),
            cap=1000,
        ),
        "registrar.StudentAcademicRecord": reader.read(
            model("registrar.StudentAcademicRecord")._base_manager.filter(
                organization_id=fixed.ORG, student_id__in=users
            ),
            cap=1500,
        ),
        "organizations.AcademicPeriod": reader.read(
            model("organizations.AcademicPeriod")._base_manager.filter(pk__in={row["period_id"] for row in offerings}),
            cap=100,
        ),
        "workload.TeachingTask": reader.read(
            model("workload.TeachingTask")._base_manager.filter(pk__in={row["task_id"] for row in allocations}), cap=100
        ),
    }
    roles = {row["role_id"] for row in context["organizations.Membership"]}
    context["organizations.Role"] = reader.read(model("organizations.Role")._base_manager.filter(pk__in=roles), cap=100)
    programs = {row["program_id"] for row in context["registrar.StudentAcademicRecord"]}
    context["registrar.Program"] = reader.read(
        model("registrar.Program")._base_manager.filter(pk__in=programs), cap=100
    )
    history_refs = {
        str(row["id"])
        for label, rows in academic.items()
        for row in rows
        if label
        in {
            "registrar.CourseOffering",
            "registrar.Enrollment",
            "registrar.Lesson",
            "registrar.LessonMark",
            "registrar.AbsenceCredit",
            "workload.TeachingTaskRow",
        }
    }
    history = collect_history(referenced_ids=history_refs)
    reversed_ids = {row["reverses_id"] for row in credits.values() if row["reverses_id"] is not None}
    identity_issues = []
    for pk, pin in fixed.OFFERINGS.items():
        row = offering_map.get(pk)
        if row is None or any(
            str(row[field]) != str(pin[field]) for field in ("subject_id", "period_id", "group_id", "instructor_id")
        ):
            identity_issues.append({"offering_id": pk, "identity_changed_or_missing": True})
    for case in fixed.CASES.values():
        enrollment = enrollments.get(case["enrollment_id"])
        if (
            enrollment is None
            or enrollment["student_id"] != case["student_id"]
            or enrollment["offering_id"] != case["offering_id"]
            or enrollment["status"] != "enrolled"
            or enrollment["superseded_by_id"] is not None
        ):
            identity_issues.append({"enrollment_id": case["enrollment_id"], "active_target_identity_changed": True})
    supersession_issues = []
    for pk, row in enrollments.items():
        if row["superseded_by_id"] is None:
            continue
        target = enrollments[row["superseded_by_id"]]
        left, right = offering_map[row["offering_id"]], offering_map[target["offering_id"]]
        if (
            row["status"] != "dropped"
            or row["student_id"] != target["student_id"]
            or any(left[field] != right[field] for field in ("subject_id", "period_id"))
        ):
            supersession_issues.append(
                {"enrollment_id": pk, "superseded_by_id": target["id"], "invalid_direct_predecessor": True}
            )
    return export_budget(
        {
            "source58_reference_graph": project(academic),
            "source58_authority_context": project(context),
            "source58_claims": claims,
            "source58_counter_preview": previews,
            "source58_typed_ledger": ledger,
            "source58_missing_typed_maps": missing_maps,
            "source58_identity_issues": identity_issues,
            "source58_supersession_issues": supersession_issues,
            "source58_source_slot_coverage": [
                {
                    "expected_lesson_id": slot["lesson_id"],
                    "offering_id": slot["offering_id"],
                    "date": slot["date"],
                    "start_time": slot["start_time"],
                    "kind": slot["kind"],
                    "same_day_current_lesson_ids": [
                        row["id"]
                        for row in lessons
                        if row["offering_id"] == slot["offering_id"] and row["date"] == slot["date"]
                    ],
                }
                for slot in fixed.SLOTS
            ],
            "source58_credit_lifecycle": [
                {
                    "id": row["id"],
                    "enrollment_id": row["enrollment_id"],
                    "hours": row["hours"],
                    "reverses_id": row["reverses_id"],
                    "active_root": row["reverses_id"] is None and row["id"] not in reversed_ids,
                    "protected_row_sha256": row["_raw_sha"],
                }
                for row in credits.values()
            ],
            **history,
            "source58_scope": [
                {
                    "organization_id": fixed.ORG,
                    "actor_id": actor,
                    "source_sha256": fixed.SOURCE_SHA256,
                    "source_cases_sha256": digest(fixed.CASES),
                    "fixed_source_cells": len(fixed.CASES),
                    "fixed_target_enrollments": len(target_ids),
                    "fixed_source_slots": len(fixed.SLOTS),
                    "missing_target_enrollment_ids": missing_targets,
                    "bounded_reference_closure_collected": True,
                    "credit_excuse_coverage": "EXPORTED_CURRENT_BOUNDED_CLOSURE",
                    "eligible_for_apply": False,
                    "registered_writer": False,
                    "history_requires_review": True,
                    "source_raw_hours_are_not_effective_delta": True,
                    "cached_mismatch_alone_is_hold": False,
                    "eligible_current_instructor_ids": sorted(eligible_instructor_ids(fixed.ORG, teachers)),
                    "protected_row_count": len(reader.seen),
                    "protected_raw_bytes": reader.bytes,
                    "protected_row_sha_policy": "postgres-row_to_json-text-utf8-sha256/1",
                    "actual_credit_rows": len(credits),
                    "formal_reference_counts": {label: len(rows) for label, rows in extra.items()},
                    "all_status_enrollment_rows": len(enrollments),
                    "credit_reversal_closure_complete": True,
                    "null_locator_lesson_corrections": sum(
                        row["lesson_id"] is None for row in extra["registrar.LessonCorrection"]
                    ),
                    "unresolved_excuse_documents": sum(
                        row["student_id"] is None for row in extra["registrar.LegacyExcuseDocument"]
                    ),
                }
            ],
        }
    )


def collect_source58_evidence():
    """Internal no-argument integration target; intentionally absent from snapshot registration."""
    try:
        with budget():
            return _capture()
    except EvidenceLimit as exc:
        return {
            "source58_scope": [
                {
                    "organization_id": fixed.ORG,
                    "source_sha256": fixed.SOURCE_SHA256,
                    "bounded_reference_closure_collected": False,
                    "credit_excuse_coverage": "UNKNOWN",
                    "status": str(exc),
                    "eligible_for_apply": False,
                    "registered_writer": False,
                }
            ]
        }
