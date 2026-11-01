"""Strict offline validator for text-free syllabus content fingerprints; no Django or DB."""

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
REGISTRY_SHA = "1783da2b28d6a669266d09f7c313ea8a4d1b59a80e76b730f2dcda20a0cc7b87"
FORMAT = "wcu-syllabus-content/1"
REGISTRY_PATH = Path(__file__).resolve().parents[2] / "apps/workload/services/chair_cells_export/batches.json"
MAX_BYTES = 8 * 1024 * 1024
KINDS = {"lecture", "seminar", "practical", "lab"}
POLICY = "exact_syllabus_recovery.digest/1"
SCHEMAS = {
    "roots": set(
        "organization_id offering_id selected_syllabus_id current_version_id stored_approved_version_id effective_approved_version_id relation lookup_complete base_candidates_complete base_candidate_count".split()
    ),
    "offerings": set("id organization_id subject_id period_id group_id instructor_id lesson_hours is_active".split()),
    "syllabi": set(
        "id organization_id subject_id offering_id period_id author_id chair_unit_id program_id is_active current_version_id approved_version_id reused_from_id created_at updated_at body_included plan_hours_override record_sha256".split()
    ),
    "versions": set(
        "id organization_id syllabus_id major minor status change_kind applies_to_period_id source_version_id completion_percent approval_source approved_by_id approved_at locked_at archived_at created_by_id submitted_by_id submitted_at reviewer_id review_started_at decided_at created_at updated_at plan_hours decision_reason_present record_sha256 canonical_policy canonical_body_sha256 course_body_sha256 known_section_count unknown_section_count topic_summary".split()
    ),
    "sections": set(
        "id organization_id version_id revision is_complete updated_by_id created_at updated_at section_id section_key_sha256 raw_data_sha256 course_data_sha256 leaf_counts is_object nonblank_string_present record_sha256".split()
    ),
    "topics": set(
        "organization_id version_id row_index valid_shape topic_present outcome_present hours hours_valid numeric_string_count row_sha256 unknown_key_count".split()
    ),
    "shares": set(
        "id organization_id syllabus_id offering_id source created_by_id created_at updated_at effective record_sha256".split()
    ),
    "cohorts": set(
        "id organization_id offering_id source_offering_id period_id department_id group_id lecture_hours seminar_hours lab_hours record_sha256".split()
    ),
    "ledger": set(
        "id organization_id source_system source_system_sha256 entity_type entity_type_sha256 legacy_numeric_id legacy_pk_sha256 target_model_label target_pk state source_row_hash record_sha256".split()
    ),
}
LEAF_KEYS = set(
    "dict_nodes list_nodes empty_lists string_leaves blank_string_leaves null_leaves boolean_leaves number_leaves".split()
)
TOPIC_SUMMARY = set(
    "row_count nonempty_topic_count hours_without_topic_count topic_without_hours_count invalid_shape_or_hours_count numeric_string_count hours_by_kind nonempty_topics_by_kind totals_complete ordered_row_sha256 row_multiset_sha256 duplicate_row_count".split()
)
ENUMS = {
    "relation": {"own", "shared", "subject_period", "base", "language_level_source", "unknown", "none"},
    "section_id": {None, "info", "desc", "out", "week", "method", "assess", "self", "lit", "prev", "send"},
    "status": {"draft", "submitted", "review", "revision", "rejected", "approved", "archived"},
    "change_kind": {"initial", "minor", "major", "copied", "imported", "reused"},
    "approval_source": {"human", "migration", "reuse", "auto"},
    "source": {"teacher", "legacy"},
    "source_system": {None, "myedu_mariadb"},
    "entity_type": {
        None,
        "worker",
        "subject",
        "group_unit",
        "syllabus",
        "syllabus_version",
        "syllabus_section",
        "journal",
        "course_offering",
    },
    "state": {"migrated", "skipped", "quarantined"},
    "canonical_policy": {POLICY},
    "target_model_label": {
        "registrar.courseoffering",
        "registrar.subject",
        "auth.user",
        "syllabus.syllabus",
        "syllabus.syllabusversion",
        "syllabus.syllabussection",
        "organizations.orgunit",
    },
}
USER_IDS = set(
    "actor_id instructor_id author_id approved_by_id created_by_id submitted_by_id reviewer_id updated_by_id legacy_numeric_id".split()
)
BOOLS = set(
    "is_active body_included lookup_complete base_candidates_complete decision_reason_present is_complete is_object nonblank_string_present valid_shape topic_present outcome_present hours_valid effective".split()
)


def fail():
    raise ValueError("syllabus_content_scope_invalid")


def is_uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def integer(value):
    return type(value) is int and 0 <= value <= 10000000000


def hours(value):
    if not isinstance(value, dict) or set(value) != KINDS:
        fail()
    if any(v is not None and not integer(v) for v in value.values()):
        fail()


def validate_nested(key, value):
    if key in {"plan_hours", "plan_hours_override"}:
        if not isinstance(value, dict) or set(value) != {"hours", "valid", "numeric_string_count", "raw_sha256"}:
            fail()
        hours(value["hours"])
        if (
            type(value["valid"]) is not bool
            or not integer(value["numeric_string_count"])
            or not re.fullmatch(r"[a-f0-9]{64}", value["raw_sha256"])
        ):
            fail()
    elif key == "hours":
        hours(value)
    elif key == "leaf_counts":
        if not isinstance(value, dict) or set(value) != LEAF_KEYS or not all(integer(v) for v in value.values()):
            fail()
    elif key == "topic_summary":
        if not isinstance(value, dict) or set(value) != TOPIC_SUMMARY:
            fail()
        for name, item in value.items():
            if name in {"hours_by_kind", "nonempty_topics_by_kind"}:
                hours(item)
            elif name == "totals_complete":
                if type(item) is not bool:
                    fail()
            elif name.endswith("sha256"):
                if not isinstance(item, str) or not re.fullmatch(r"[a-f0-9]{64}", item):
                    fail()
            elif not integer(item):
                fail()


def validate_scalar(key, value):
    if key in USER_IDS:
        if value is not None and not integer(value):
            fail()
    elif key in ENUMS:
        if not isinstance(value, (str, type(None))) or value not in ENUMS[key]:
            fail()
    elif key in BOOLS:
        if type(value) is not bool:
            fail()
    elif key.endswith("sha256") or key == "source_row_hash":
        if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
            fail()
    elif key.endswith("_at"):
        if value is not None:
            if not isinstance(value, str) or len(value) > 40:
                fail()
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                fail()
    elif key == "id" or key.endswith("_id"):
        if value is not None and not is_uuid(value):
            fail()
    elif key == "target_pk":
        if not is_uuid(value) and not (
            isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 10
        ):
            fail()
    elif not integer(value):
        fail()


def reject_cycles(data):
    for objects, pointer in (
        ({row["id"]: row for row in data["versions"]}, "source_version_id"),
        ({row["id"]: row for row in data["syllabi"] if row["body_included"]}, "reused_from_id"),
    ):
        for start in objects:
            current, seen = start, set()
            while current in objects:
                if current in seen:
                    fail()
                seen.add(current)
                current = objects[current][pointer]


def validate(payload):
    return _validate(payload)


def _validate(payload, *, _forensic=False):
    schemas = SCHEMAS
    forensic = None
    if _forensic:
        import importlib.util

        path = Path(__file__).resolve().parents[2] / "apps/workload/services/syllabus_forensic_spec.py"
        definition = importlib.util.spec_from_file_location("fixed_body_forensics", path)
        forensic = importlib.util.module_from_spec(definition)
        definition.loader.exec_module(forensic)
        schemas = {**SCHEMAS, **forensic.SCHEMAS}
    if not isinstance(payload, dict):
        fail()
    if len(json.dumps(payload, ensure_ascii=False).encode()) > MAX_BYTES:
        fail()
    top = set(
        "format organization_id academic_year period_id batch registry_sha256 captured_at actor_id read_only eligible_for_apply selection coverage data counts schema_fields".split()
    )
    if set(payload) != top or (
        payload.get("format"),
        payload.get("organization_id"),
        payload.get("academic_year"),
        payload.get("period_id"),
        payload.get("registry_sha256"),
    ) != (forensic.FORMAT if _forensic else FORMAT, ORG, "2026/2027", PERIOD, REGISTRY_SHA):
        fail()
    if (
        payload["read_only"] is not True
        or payload["eligible_for_apply"] is not False
        or not isinstance(payload["batch"], str)
        or not re.fullmatch(r"chair-cells-\d{3}", payload["batch"])
    ):
        fail()
    if _forensic and payload["batch"] not in forensic.BATCHES:
        fail()
    encoded = REGISTRY_PATH.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != REGISTRY_SHA:
        fail()
    expected = json.loads(encoded)["batches"].get(payload["batch"])
    if expected != payload["selection"] or (_forensic and len(expected["offerings"]) != 20):
        fail()
    validate_scalar("captured_at", payload["captured_at"])
    validate_scalar("actor_id", payload["actor_id"])
    if type(payload["actor_id"]) is not int or payload["actor_id"] <= 0:
        fail()
    data = payload["data"]
    if (
        not isinstance(data, dict)
        or set(data) != set(schemas)
        or not isinstance(payload["counts"], dict)
        or set(payload["counts"]) != set(schemas)
        or not isinstance(payload["schema_fields"], dict)
        or set(payload["schema_fields"]) != set(schemas)
    ):
        fail()
    caps = {
        "roots": 25,
        "offerings": 25,
        "syllabi": 1500,
        "versions": 500,
        "sections": 5000,
        "topics": 100000,
        "shares": 1500,
        "cohorts": 25,
        "ledger": 5000,
    }
    if _forensic:
        caps.update(lineage_edges=4000, lineage_cycles=800, held_roots=25)
    if any(not isinstance(v, list) for v in data.values()) or sum(len(v) for v in data.values()) > 110000:
        fail()
    for table, values in data.items():
        if (
            not isinstance(values, list)
            or len(values) > caps[table]
            or type(payload["counts"][table]) is not int
            or payload["counts"][table] != len(values)
        ):
            fail()
        if payload["schema_fields"][table] != (sorted(schemas[table]) if values else []):
            fail()
        for row in values:
            if _forensic and table in forensic.SCHEMAS:
                if not isinstance(row, dict) or set(row) != schemas[table]:
                    fail()
                if table == "held_roots" and (
                    row["organization_id"] != ORG
                    or not is_uuid(row["offering_id"])
                    or type(row["lineage_cycle_affected"]) is not bool
                ):
                    fail()
                continue
            if not isinstance(row, dict) or set(row) != schemas[table] or row["organization_id"] != ORG:
                fail()
            if "id" in row and not is_uuid(row["id"]):
                fail()
            for key, value in row.items():
                if key in {"plan_hours", "plan_hours_override", "hours", "leaf_counts", "topic_summary"}:
                    validate_nested(key, value)
                else:
                    validate_scalar(key, value)
    roots = {r["offering_id"] for r in data["roots"]}
    if len(roots) != len(data["roots"]) or roots != {r["id"] for r in expected["offerings"]}:
        fail()
    coverage = payload["coverage"]
    if not isinstance(coverage, dict) or any(
        type(coverage.get(key)) is not bool
        for key in (
            "lookup_complete",
            "closure_complete",
            "truncated",
            "base_candidates_metadata_only",
            "absence_claim",
            "automatic_content_verdict",
        )
    ):
        fail()
    if _forensic and (
        any(
            type(coverage.get(key)) is not bool
            for key in ("lineage_visited_complete", "lineage_integrity", "normal_content_export_usable")
        )
        or type(coverage.get("cycle_affected_root_count")) is not int
    ):
        fail()
    expected_coverage = {
        "lookup_complete": True,
        "closure_complete": True,
        "truncated": False,
        "canonical_hash_policy": POLICY,
        "body_scope": "selected_owned_current_approved_ancestry",
        "base_candidates_metadata_only": True,
        "root_count": len(roots),
        "course_context_count": len(data["offerings"]),
        "absence_claim": False,
        "automatic_content_verdict": False,
    }
    if _forensic:
        expected_coverage.update(
            closure_complete=False,
            lineage_visited_complete=True,
            lineage_integrity=False,
            normal_content_export_usable=False,
            cycle_affected_root_count=sum(r["lineage_cycle_affected"] is True for r in data["held_roots"]),
        )
    if coverage != expected_coverage:
        fail()
    offering_ids = {r["id"] for r in data["offerings"]}
    syllabus_ids = {r["id"] for r in data["syllabi"]}
    version_ids = {r["id"] for r in data["versions"]}
    if not roots <= offering_ids or any(r["period_id"] != PERIOD for r in data["offerings"] if r["id"] in roots):
        fail()
    for root in data["roots"]:
        if root["selected_syllabus_id"] is not None and root["selected_syllabus_id"] not in syllabus_ids:
            fail()
        for name in ("current_version_id", "stored_approved_version_id", "effective_approved_version_id"):
            if root[name] is not None and root[name] not in version_ids:
                fail()
    for version in data["versions"]:
        if (
            version["syllabus_id"] not in syllabus_ids
            or version["source_version_id"] is not None
            and version["source_version_id"] not in version_ids
        ):
            fail()
    for row in [*data["sections"], *data["topics"]]:
        if row["version_id"] not in version_ids:
            fail()
    for share in data["shares"]:
        if share["offering_id"] not in roots or share["syllabus_id"] not in syllabus_ids:
            fail()

    for table in ("offerings", "syllabi", "versions", "sections", "shares", "cohorts", "ledger"):
        if len({r["id"] for r in data[table]}) != len(data[table]):
            fail()
    if len({(r["version_id"], r["row_index"]) for r in data["topics"]}) != len(data["topics"]):
        fail()
    version_map = {r["id"]: r for r in data["versions"]}
    for root in data["roots"]:
        if root["lookup_complete"] is not True or root["base_candidates_complete"] is not True:
            fail()
        for key in ("current_version_id", "stored_approved_version_id", "effective_approved_version_id"):
            pointer = root[key]
            if pointer is not None and version_map[pointer]["syllabus_id"] != root["selected_syllabus_id"]:
                fail()
        effective = root["effective_approved_version_id"]
        if effective is not None and version_map[effective]["status"] != "approved":
            fail()
    for syllabus in data["syllabi"]:
        if syllabus["body_included"]:
            if syllabus["reused_from_id"] is not None and syllabus["reused_from_id"] not in syllabus_ids:
                fail()
            for key in ("current_version_id", "approved_version_id"):
                pointer = syllabus[key]
                if pointer is not None and (
                    pointer not in version_map or version_map[pointer]["syllabus_id"] != syllabus["id"]
                ):
                    fail()
    for share in data["shares"]:
        if share["effective"] and not any(
            r["offering_id"] == share["offering_id"] and r["selected_syllabus_id"] == share["syllabus_id"]
            for r in data["roots"]
        ):
            fail()

    if not _forensic:
        reject_cycles(data)
    if _forensic:
        import importlib.util

        definition = importlib.util.spec_from_file_location(
            "fixed_lineage_graph", Path(__file__).with_name("syllabus_lineage_scope.py")
        )
        graph_module = importlib.util.module_from_spec(definition)
        definition.loader.exec_module(graph_module)
        expected_analysis = forensic.analysis(data, graph_builder=graph_module.contract.graph)
        if any(data[table] != rows for table, rows in expected_analysis.items()):
            fail()
