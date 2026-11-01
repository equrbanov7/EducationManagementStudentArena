"""Pure output allowlist: typed references, enums, counters and hashes only."""

import json
import re
import uuid
from datetime import datetime

from . import spec

HEADERS = set(
    "format organization_id academic_year period_id subject_ids source_namespace source_sha256 source_ids_sha256 source_rows_sha256 source_captured_at captured_at actor_id read_only eligible_for_apply immutable_mapping data coverage counts".split()
)
SCHEMAS = {
    "identity": "source_id source_row_sha256 source_fin_sha256 source_fin_valid source_fin_duplicate target_user_id method evidence_methods same_tenant_candidate_user_ids reasons immutable_mapping",
    "profiles": "user_id organization_id access_state is_deleted blocked_at deleted_at user__is_active updated_at",
    "memberships": "id organization_id user_id role_id scope_unit_id is_active role__is_active role__organization_id created_at updated_at",
    "academic_records": "id organization_id student_id program_id curriculum_id group_id admission_year status is_active national_athlete_exemption created_at updated_at",
    "offerings": "id organization_id subject_id period_id group_id instructor_id is_active lesson_hours course_format created_at updated_at",
    "cohorts": "id organization_id department_id group_id offering_id period_id source_offering_id lecture_hours seminar_hours lab_hours created_by_id created_at updated_at name_sha256 family_sha256 level",
    "placements": "id organization_id cohort_id student_id home_group_id action source_enrollment_id target_enrollment_id actor_id created_at updated_at reason_present reason_sha256",
    "enrollments": "id organization_id offering_id student_id kind status source_group_id superseded_by_id added_by_id created_at updated_at",
    "mark_activity": "enrollment_id mark_count numeric_count absent_count excused_count human_actor_count latest_created_at latest_updated_at latest_human_updated_at",
    "identity_ledger_proofs": "id organization_id source_id target_user_id target_reference_sha256 source_row_hash updated_at",
    "groups": "id organization_id parent_id unit_type is_active sector language_sector language sector_unrecognized language_sector_unrecognized language_unrecognized language_level_cohort settings_sha256",
}
SCHEMAS.update(
    {
        "teachers": "user_id user_is_active profile_present profile_in_fixed_tenant access_state profile_updated_at profile_is_deleted profile_blocked_at profile_deleted_at active_org_membership grade_input_role_active is_current_owner has_positive_current_assignment has_journal_share",
        "teacher_memberships": "id organization_id user_id role_id scope_unit_id is_active role__is_active role__organization_id role__scope_type created_at updated_at grade_input_role",
        "assignments": "id organization_id row_id teacher_id activity hours is_hourly_paid created_at updated_at groups_note_present groups_note_sha256",
        "assignment_group_links": "link_id row_id group_id",
        "shares": "id organization_id offering_id teacher_id kinds source is_active created_by_id created_at updated_at batch_sha256",
        "share_links": "link_id share_id enrollment_id",
    }
)
SCHEMAS = {key: set(value.split()) for key, value in SCHEMAS.items()}
REASONS = {
    "ledger_target_outside_same_tenant_profiles",
    "source_identity_duplicate",
    "ambiguous_ledger",
    "ambiguous_institutional",
    "ambiguous_fin",
    "identity_evidence_contradiction",
    "source_target_fin_disagrees",
    "source_target_institutional_disagrees",
    "no_exact_identity_match",
}
ENUMS = {
    "access_state": {"active", "staged", "archived"},
    "method": {"ledger", "institutional", "fin"},
    "activity": {"lecture", "seminar", "lab"},
    "source": {"legacy", "manual", "workload"},
    "role__scope_type": {"organization", "unit", "course"},
    "action": {"add", "remove", "move"},
    "course_format": {"regular", "intensive"},
    "kind": {"mandatory", "elective", "retake"},
    "status": {
        "enrolled",
        "dropped",
        "completed",
        "suspended",
        "academic_leave",
        "graduated",
        "expelled",
        "transferred",
    },
    "unit_type": {
        "group",
        "chair",
        "department",
        "faculty",
        "specialty",
        "university",
        "branch",
        "campus",
    },
    "level": {
        "beginner",
        "elementary",
        "pre-intermediate",
        "intermediate",
        "upper-intermediate",
        "advanced",
        "a1",
        "a2",
        "b1",
        "b2",
        "c1",
        "c2",
    },
    "sector": {"az", "en", "ru"},
    "language_sector": {"az", "en", "ru"},
    "language": {"az", "en", "ru"},
}
INTEGERS = set(
    "link_id source_id target_user_id user_id student_id teacher_id instructor_id actor_id added_by_id created_by_id hours admission_year lesson_hours lecture_hours seminar_hours lab_hours mark_count numeric_count absent_count excused_count human_actor_count".split()
)
BOOLS = set(
    "is_deleted profile_is_deleted user_is_active profile_present profile_in_fixed_tenant active_org_membership grade_input_role_active is_current_owner has_positive_current_assignment has_journal_share grade_input_role is_hourly_paid groups_note_present source_fin_valid source_fin_duplicate user__is_active is_active role__is_active national_athlete_exemption reason_present sector_unrecognized language_sector_unrecognized language_unrecognized language_level_cohort immutable_mapping".split()
)


def _value(key, value):
    if value is None:
        if (key in BOOLS and key != "profile_is_deleted") or key in {
            "evidence_methods",
            "reasons",
            "same_tenant_candidate_user_ids",
        }:
            raise ValueError("english_level_required_value_missing")
        return
    if key in INTEGERS:
        if type(value) is not int or value < 0:
            raise ValueError("english_level_integer_invalid")
    elif key in BOOLS:
        if type(value) is not bool:
            raise ValueError("english_level_boolean_invalid")
    elif key.endswith("_sha256") or key == "source_row_hash":
        if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
            raise ValueError("english_level_hash_invalid")
    elif key.endswith("_at"):
        if not isinstance(value, str) or datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is None:
            raise ValueError("english_level_timestamp_invalid")
    elif key in ENUMS:
        if value not in ENUMS[key]:
            raise ValueError("english_level_enum_invalid")
    elif key == "kinds":
        if not isinstance(value, list) or any(v not in ("lecture", "seminar", "lab") for v in value):
            raise ValueError("english_level_share_kinds_invalid")
    elif key == "evidence_methods":
        if not isinstance(value, list) or any(v not in ENUMS["method"] for v in value):
            raise ValueError("english_level_methods_invalid")
    elif key == "reasons":
        if not isinstance(value, list) or any(v not in REASONS for v in value):
            raise ValueError("english_level_reasons_invalid")
    elif key == "same_tenant_candidate_user_ids":
        if not isinstance(value, list) or any(type(v) is not int or v <= 0 for v in value):
            raise ValueError("english_level_candidate_ids_invalid")
    else:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError("english_level_uuid_invalid")


def validate(payload):
    if set(payload) != HEADERS or (
        payload["format"],
        payload["organization_id"],
        payload["academic_year"],
        payload["period_id"],
    ) != (spec.FORMAT, spec.ORG, spec.YEAR, spec.PERIOD):
        raise ValueError("english_level_output_scope_invalid")
    if payload["source_namespace"] != "myedu_new.students.id":
        raise ValueError("english_level_output_namespace_invalid")
    if (
        payload["subject_ids"] != list(spec.SUBJECTS)
        or payload["source_sha256"] != spec.SOURCE_SHA
        or payload["source_ids_sha256"] != spec.SOURCE_IDS_SHA
    ):
        raise ValueError("english_level_output_source_pin_changed")
    if (
        payload["read_only"] is not True
        or payload["eligible_for_apply"] is not False
        or payload["immutable_mapping"] is not False
    ):
        raise ValueError("english_level_output_authority_invalid")
    if set(payload["data"]) != set(SCHEMAS) or set(payload["counts"]) != set(SCHEMAS):
        raise ValueError("english_level_output_tables_invalid")
    if any(value is not False for value in payload["coverage"].values()) or set(payload["coverage"]) != set(
        "written_marks_exported raw_lesson_marks_exported identity_creates_or_mutations archive_filter_applied teacher_access_attested".split()
    ):
        raise ValueError("english_level_output_coverage_invalid")
    for key in ("source_rows_sha256", "source_captured_at", "captured_at", "actor_id"):
        if payload[key] is None:
            raise ValueError("english_level_output_proof_missing")
        _value(key, payload[key])
    if type(payload["actor_id"]) is not int or payload["actor_id"] <= 0:
        raise ValueError("english_level_output_actor_invalid")
    for name, rows in payload["data"].items():
        if not isinstance(rows, list) or payload["counts"][name] != len(rows):
            raise ValueError("english_level_output_count_invalid")
        pk = {
            "identity": "source_id",
            "profiles": "user_id",
            "teachers": "user_id",
            "mark_activity": "enrollment_id",
            "share_links": "link_id",
            "assignment_group_links": "link_id",
        }.get(name, "id")
        if any(row.get(pk) is None or (type(row.get(pk)) is int and row[pk] <= 0) for row in rows):
            raise ValueError("english_level_output_primary_id_invalid")
        if len({row[pk] for row in rows}) != len(rows):
            raise ValueError("english_level_output_duplicate_id")
        for row in rows:
            if set(row) != SCHEMAS[name]:
                raise ValueError("english_level_output_schema_or_privacy_invalid")
            for key, value in row.items():
                _value(key, value)
            if any(row.get(key, spec.ORG) != spec.ORG for key in ("organization_id", "role__organization_id")):
                raise ValueError("english_level_output_foreign_tenant")
            if row.get("immutable_mapping") not in (None, False):
                raise ValueError("english_level_immutable_mapping_forbidden")
    data = payload["data"]
    for row in data["identity"]:
        if row["source_row_sha256"] is None or (row["source_fin_valid"] != (row["source_fin_sha256"] is not None)):
            raise ValueError("english_level_identity_source_proof_invalid")
        resolved = row["target_user_id"] is not None
        if resolved != (row["method"] is not None) or resolved == bool(row["reasons"]):
            raise ValueError("english_level_identity_result_invalid")
        if resolved and (
            row["target_user_id"] not in row["same_tenant_candidate_user_ids"]
            or row["method"] not in row["evidence_methods"]
        ):
            raise ValueError("english_level_identity_evidence_invalid")
    if (
        len(data["teachers"]) > spec.MAX_TEACHERS
        or len(data["share_links"]) > spec.MAX_SHARE_LINKS
        or len(data["assignment_group_links"]) > spec.MAX_SHARE_LINKS
    ):
        raise ValueError("english_level_output_staff_budget_exceeded")
    if (
        len(data["offerings"]) > spec.MAX_COURSES
        or len(data["enrollments"]) > spec.MAX_ENROLLMENTS
        or len(data["placements"]) > spec.MAX_PLACEMENTS
        or sum(map(len, data.values())) > spec.MAX_ROWS
    ):
        raise ValueError("english_level_output_row_budget_exceeded")
    if (
        len(data["identity"]) != spec.SOURCE_COUNT
        or __import__("hashlib")
        .sha256(json.dumps([r["source_id"] for r in data["identity"]], separators=(",", ":")).encode())
        .hexdigest()
        != spec.SOURCE_IDS_SHA
    ):
        raise ValueError("english_level_output_source_id_set_changed")
    courses = {r["id"]: r for r in data["offerings"]}
    enrollments = {r["id"]: r for r in data["enrollments"]}
    cohorts = {r["id"]: r for r in data["cohorts"]}
    profiles = {r["user_id"] for r in data["profiles"]}
    if any(r["period_id"] != spec.PERIOD or r["subject_id"] not in spec.SUBJECTS for r in courses.values()):
        raise ValueError("english_level_output_foreign_course")
    if any(
        r["offering_id"] not in courses
        or r["student_id"] not in profiles
        or (r["superseded_by_id"] and r["superseded_by_id"] not in enrollments)
        for r in enrollments.values()
    ):
        raise ValueError("english_level_output_enrollment_closure_invalid")
    if any(
        r["offering_id"] not in courses
        or r["period_id"] != spec.PERIOD
        or (r["source_offering_id"] and r["source_offering_id"] not in courses)
        for r in cohorts.values()
    ):
        raise ValueError("english_level_output_cohort_closure_invalid")
    if any(
        r["cohort_id"] not in cohorts
        or r["student_id"] not in profiles
        or any(r[k] and r[k] not in enrollments for k in ("source_enrollment_id", "target_enrollment_id"))
        for r in data["placements"]
    ):
        raise ValueError("english_level_output_placement_closure_invalid")
    if any(r["enrollment_id"] not in enrollments for r in data["mark_activity"]):
        raise ValueError("english_level_output_activity_closure_invalid")
    if any(
        (r["target_user_id"] is not None and r["target_user_id"] not in profiles)
        or not set(r["same_tenant_candidate_user_ids"]) <= profiles
        for r in data["identity"]
    ):
        raise ValueError("english_level_output_identity_closure_invalid")
    teacher_ids = {r["user_id"] for r in data["teachers"]}
    shares = {r["id"]: r for r in data["shares"]}
    if any(r["offering_id"] not in courses or r["teacher_id"] not in teacher_ids for r in shares.values()):
        raise ValueError("english_level_output_share_scope_invalid")
    if any(
        r["share_id"] not in shares
        or r["enrollment_id"] not in enrollments
        or enrollments[r["enrollment_id"]]["offering_id"] != shares[r["share_id"]]["offering_id"]
        for r in data["share_links"]
    ):
        raise ValueError("english_level_output_share_roster_scope_invalid")
    if any(r["teacher_id"] not in teacher_ids for r in data["assignments"]) or any(
        r["user_id"] not in teacher_ids for r in data["teacher_memberships"]
    ):
        raise ValueError("english_level_output_teacher_scope_invalid")
    assignment_rows = {r["row_id"] for r in data["assignments"]}
    if any(r["row_id"] not in assignment_rows for r in data["assignment_group_links"]):
        raise ValueError("english_level_output_assignment_scope_invalid")
    if len(json.dumps(payload, sort_keys=True).encode()) > spec.MAX_BYTES:
        raise ValueError("english_level_output_byte_budget_exceeded")
    return payload
