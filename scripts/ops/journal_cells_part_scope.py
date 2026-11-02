"""Standalone strict reviewed fixed partitions: old cell schemas and full bounded closure."""

import copy
import hashlib
import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_SHA = "52e620563eea6080993111f9e51bf8f0a9f5689115bd3632e0dcb3048b45773d"
PARENTS = tuple(f"chair-cells-{number:03}" for number in (40, 43, 53, 64, 65, 66, 67, 68, 69, 70))
PARTS = tuple(f"{parent}-part-{index:03}" for parent in PARENTS for index in (1, 2))
FORMAT = "wcu-journal-cells-part/1"
POLICY = "wcu-chair-cells-reviewed-halves/1"
MAX_BYTES = 128 * 1024 * 1024
CLASSIFICATION = "Snapshot chair metadata only; unresolved is unassigned. No write authority."
HEADERS = set(
    "format organization_id academic_year period_id batch registry_sha256 captured_at actor_id selection read_only eligible_for_apply correction_coverage classification schema_fields data counts parent_batch part part_count partition_policy parent_selection_sha256".split()
)
GAPS = set(
    "journal_correction_outside_captured_refs selfwork_corrections_outside_captured_course component_corrections_outside_captured_course tenant_deleted_lesson_corrections_unlocatable".split()
)


def old_scope():
    spec = importlib.util.spec_from_file_location(
        "journal_cells_pinned_schema", Path(__file__).with_name("journal_cells_scope.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parent_spec(name):
    if name not in PARENTS:
        raise ValueError("fixed_part_parent_required")
    raw = (ROOT / "apps/workload/services/chair_cells_export/batches.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != REGISTRY_SHA:
        raise ValueError("part_parent_registry_changed")
    return json.loads(raw)["batches"][name]


def selection(part):
    if part not in PARTS:
        raise ValueError("fixed_part_required")
    parent = parent_spec(part.split("-part-")[0])
    if len(parent["offerings"]) != 20:
        raise ValueError("fixed_parent_twenty_roots_required")
    result = copy.deepcopy(parent)
    offset = (int(part.rsplit("-", 1)[1]) - 1) * 10
    result["offerings"] = result["offerings"][offset : offset + 10]
    return result, hashlib.sha256(json.dumps(parent, sort_keys=True).encode()).hexdigest()


def _table(rows):
    result = {row["id"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate_part_row_id")
    return result


def _references(data):
    courses, enrollments, lessons, marks = (
        _table(data[key]) for key in ("offerings", "enrollments", "lessons", "marks")
    )
    if any(r["offering_id"] not in courses for r in [*enrollments.values(), *lessons.values()]):
        raise ValueError("part_content_outside_courses")
    edges = {pk: set() for pk in courses}
    for row in enrollments.values():
        successor = row["superseded_by_id"]
        if successor is None:
            continue
        if successor not in enrollments:
            raise ValueError("part_supersession_outside_closure")
        other = enrollments[successor]
        # Actual stored edges are audit evidence, never guessed subject identity.
        left, right = row["offering_id"], other["offering_id"]
        edges[left].add(right)
        edges[right].add(left)
    if any(r["lesson_id"] not in lessons or r["enrollment_id"] not in enrollments for r in marks.values()):
        raise ValueError("part_mark_outside_closure")
    for row in data["journal_corrections"]:
        if row["lesson_ref"] not in lessons or row["enrollment_ref"] not in enrollments:
            raise ValueError("part_journal_correction_outside_closure")
        if row["lesson_mark_id"] is not None and row["lesson_mark_id"] not in marks:
            raise ValueError("part_journal_mark_outside_closure")
    if any(row["lesson_id"] not in lessons for row in data["lesson_corrections"]):
        raise ValueError("part_lesson_correction_outside_closure")
    for table in ("selfwork_corrections", "component_corrections", "coursework_corrections", "hygiene_decisions"):
        if any(row["enrollment_id"] not in enrollments for row in data[table]):
            raise ValueError("part_enrollment_evidence_outside_closure")
    for row in data["correction_reversals"]:
        refs = [
            (table, row[table.removesuffix("s") + "_id"])
            for table in (
                "journal_corrections",
                "lesson_corrections",
                "selfwork_corrections",
                "component_corrections",
                "coursework_corrections",
            )
        ]
        present = [(table, pk) for table, pk in refs if pk is not None]
        if len(present) != 1 or present[0][1] not in {r["id"] for r in data[present[0][0]]}:
            raise ValueError("part_reversal_outside_closure")
    users = {str(r["student_id"]) for r in enrollments.values()}
    for rows, fields in (
        (courses.values(), ("instructor_id",)),
        (lessons.values(), ("instructor_id", "created_by_id")),
        (marks.values(), ("entered_by_id",)),
    ):
        users.update(str(row[field]) for row in rows for field in fields if row[field] is not None)
    allowed = {
        "registrar.courseoffering": set(courses),
        "registrar.enrollment": set(enrollments),
        "registrar.lesson": set(lessons),
        "registrar.lessonmark": set(marks),
        "auth.user": users,
        "registrar.subject": {r["subject_id"] for r in courses.values()},
        "organizations.orgunit": {r["group_id"] for r in courses.values() if r["group_id"] is not None},
    }
    for row in data["ledger"]:
        if (
            row["source_system"] != "myedu_mariadb"
            or row["target_pk"] not in allowed.get(row["target_model_label"], set())
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._-]{0,254}", row["legacy_pk"])
        ):
            raise ValueError("part_ledger_outside_typed_scope")
    return courses, edges


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != HEADERS:
        raise ValueError("part_header_schema_invalid")
    expected, parent_sha = selection(payload["part"])
    if (
        payload["format"] != FORMAT
        or payload["batch"] != payload["part"].split("-part-")[0]
        or payload["parent_batch"] != payload["part"].split("-part-")[0]
        or type(payload["part_count"]) is not int
        or payload["part_count"] != 2
        or payload["partition_policy"] != POLICY
        or payload["registry_sha256"] != REGISTRY_SHA
        or payload["parent_selection_sha256"] != parent_sha
        or payload["selection"] != expected
        or payload["academic_year"] != "2026/2027"
        or payload["classification"] != CLASSIFICATION
        or type(payload["actor_id"]) is not int
        or payload["actor_id"] < 1
    ):
        raise ValueError("part_identity_invalid")
    try:
        captured = datetime.fromisoformat(payload["captured_at"])
    except (ValueError, TypeError):
        raise ValueError("part_capture_time_invalid") from None
    if captured.tzinfo is None:
        raise ValueError("part_capture_time_invalid")
    schema = old_scope()
    schema.validate(payload)
    if set(payload["schema_fields"]) != schema.TABLES or set(payload["counts"]) != schema.TABLES:
        raise ValueError("part_table_schema_invalid")
    for table in schema.TABLES:
        if (
            not isinstance(payload["data"][table], list)
            or len(payload["schema_fields"][table]) != len(schema.SCHEMAS[table])
            or type(payload["counts"][table]) is not int
        ):
            raise ValueError("part_table_count_or_schema_invalid")
        _table(payload["data"][table])
    evidence = payload["correction_coverage"]
    if (
        set(evidence) != {"coverage_gaps", "override_proof_complete", "deleted_unlocatable_evidence_rule"}
        or set(evidence["coverage_gaps"]) != GAPS
        or any(type(v) is not int or v < 0 for v in evidence["coverage_gaps"].values())
        or type(evidence["override_proof_complete"]) is not bool
        or evidence["override_proof_complete"] != (not any(evidence["coverage_gaps"].values()))
        or evidence["deleted_unlocatable_evidence_rule"]
        != "Tenant-wide count only, not assignable to this batch; retain candidate on hold."
    ):
        raise ValueError("part_correction_coverage_invalid")
    courses, edges = _references(payload["data"])
    reached = {row["id"] for row in expected["offerings"]}
    if not reached <= set(courses):
        raise ValueError("part_seed_missing")
    while True:
        extended = reached | {other for pk in reached for other in edges[pk]}
        if extended == reached:
            break
        reached = extended
    if reached != set(courses):
        raise ValueError("part_unconnected_extra_course")
    return payload


def validate_pair(first, second):
    """Return only logical coverage metadata, never a merged authenticated envelope."""
    validate(first)
    validate(second)
    parent = first["parent_batch"]
    if second["parent_batch"] != parent or [first["part"], second["part"]] != [
        parent + "-part-001",
        parent + "-part-002",
    ]:
        raise ValueError("part_pair_identity_invalid")
    seeds = {row["id"] for payload in (first, second) for row in payload["selection"]["offerings"]}
    if seeds != {row["id"] for row in parent_spec(parent)["offerings"]}:
        raise ValueError("part_pair_parent_seeds_incomplete")
    for table in old_scope().TABLES:
        left, right = _table(first["data"][table]), _table(second["data"][table])
        if any(left[pk] != right[pk] for pk in set(left) & set(right)):
            raise ValueError("temporal_overlap_drift")
    return {
        "batch": parent,
        "proof_type": "authenticated_parts",
        "complete": True,
        "part_names": [first["part"], second["part"]],
        "seed_offerings": len(seeds),
        "overlap_consistent": True,
        "reason_code": None,
    }
