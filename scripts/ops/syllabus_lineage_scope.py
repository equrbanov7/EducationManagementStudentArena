"""Strict text-free, fixed027 diagnostic schema; never normal content evidence."""

import importlib.util
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "apps/workload/services/syllabus_lineage_spec.py"
module_spec = importlib.util.spec_from_file_location("fixed_lineage_contract", PATH)
contract = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(contract)
MAX_BYTES = contract.MAX_BYTES
USER_IDS = {"actor_id", "instructor_id", "author_id", "approved_by_id"}
TIMES = {"created_at", "updated_at", "approved_at"}
ENUMS = {
    "status": {"draft", "submitted", "review", "revision", "rejected", "approved", "archived"},
    "approval_source": {"human", "migration", "reuse", "auto"},
}


def fail():
    raise ValueError("syllabus_lineage_scope_invalid")


def is_uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _time(value):
    try:
        return isinstance(value, str) and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def validate(value):
    top = set(
        "format organization_id period_id academic_year batch registry_sha256 captured_at actor_id read_only eligible_for_apply selection coverage data counts".split()
    )
    if not isinstance(value, dict) or set(value) != top or len(json.dumps(value).encode()) > MAX_BYTES:
        fail()
    for key, expected in (
        ("format", contract.FORMAT),
        ("organization_id", contract.ORG),
        ("period_id", contract.PERIOD),
        ("academic_year", contract.YEAR),
        ("batch", contract.BATCH),
        ("registry_sha256", contract.REGISTRY_SHA),
    ):
        if value[key] != expected:
            fail()
    if type(value["actor_id"]) is not int or value["actor_id"] <= 0 or not _time(value["captured_at"]):
        fail()
    if (
        value["read_only"] is not True
        or value["eligible_for_apply"] is not False
        or value["selection"] != contract.selection()
    ):
        fail()
    if not isinstance(value["coverage"], dict) or any(type(item) is not bool for item in value["coverage"].values()):
        fail()
    if value["coverage"] != dict(
        closure_complete=True,
        truncated=False,
        bodies_included=False,
        absence_claim=False,
        normal_content_export_usable=False,
    ):
        fail()
    data = value["data"]
    if (
        not isinstance(data, dict)
        or set(data) != set(contract.SCHEMAS)
        or not isinstance(value["counts"], dict)
        or set(value["counts"]) != set(data)
    ):
        fail()
    caps = {
        "roots": 25,
        "offerings": 25,
        "syllabi": 300,
        "versions": 500,
        "edges": 1400,
        "cycles": 800,
        "owner_mismatches": 600,
    }
    for key, rows in data.items():
        if (
            not isinstance(rows, list)
            or len(rows) > caps[key]
            or type(value["counts"][key]) is not int
            or value["counts"][key] != len(rows)
        ):
            fail()
        for row in rows:
            if not isinstance(row, dict) or set(row) != contract.SCHEMAS[key]:
                fail()
            if key in {"edges", "cycles", "owner_mismatches"}:
                continue  # Exact graph equality below validates every scalar and nested cycle ID.
            for field, item in row.items():
                if field == "organization_id":
                    if item != contract.ORG:
                        fail()
                elif field in USER_IDS:
                    if item is not None and (type(item) is not int or item <= 0):
                        fail()
                elif field in TIMES:
                    if not (field == "approved_at" and item is None) and not _time(item):
                        fail()
                elif field == "record_sha256":
                    if not isinstance(item, str) or not re.fullmatch(r"[a-f0-9]{64}", item):
                        fail()
                elif field == "is_active":
                    if type(item) is not bool:
                        fail()
                elif field == "lesson_hours":
                    if type(item) is not int or not 0 <= item <= 100000:
                        fail()
                elif field in ENUMS:
                    if not isinstance(item, str) or item not in ENUMS[field]:
                        fail()
                elif item is not None and not is_uuid(item):
                    fail()
    maps = {}
    for key in ("offerings", "syllabi", "versions"):
        maps[key] = {r["id"]: r for r in data[key]}
        if None in maps[key] or len(maps[key]) != len(data[key]):
            fail()
    roots = {r["offering_id"] for r in data["roots"]}
    if roots != {r["id"] for r in value["selection"]["offerings"]} or len(roots) != len(data["roots"]):
        fail()
    sy, ve, courses = maps["syllabi"], maps["versions"], maps["offerings"]
    for row in data["roots"]:
        if row["offering_id"] not in courses or courses[row["offering_id"]]["period_id"] != contract.PERIOD:
            fail()
        for field, targets in (("selected_syllabus_id", sy), ("effective_approved_version_id", ve)):
            if row[field] is not None and row[field] not in targets:
                fail()
    for row in sy.values():
        for field, targets in (
            ("current_version_id", ve),
            ("approved_version_id", ve),
            ("reused_from_id", sy),
            ("offering_id", courses),
        ):
            if row[field] is not None and row[field] not in targets:
                fail()
    if set(courses) != roots | {row["offering_id"] for row in sy.values() if row["offering_id"] is not None}:
        fail()
    for row in ve.values():
        if row["syllabus_id"] not in sy or row["source_version_id"] is not None and row["source_version_id"] not in ve:
            fail()
    reachable_s = {key for key, row in sy.items() if row["offering_id"] in roots}
    reachable_s |= {row["selected_syllabus_id"] for row in data["roots"] if row["selected_syllabus_id"]}
    reachable_v = {
        row["effective_approved_version_id"] for row in data["roots"] if row["effective_approved_version_id"]
    }
    while True:
        prior = (len(reachable_s), len(reachable_v))
        for key in tuple(reachable_s):
            row = sy[key]
            if row["reused_from_id"]:
                reachable_s.add(row["reused_from_id"])
            reachable_v.update(row[field] for field in ("current_version_id", "approved_version_id") if row[field])
        reachable_v.update(
            key for key, row in ve.items() if row["syllabus_id"] in reachable_s and row["status"] == "approved"
        )
        for key in tuple(reachable_v):
            row = ve[key]
            reachable_s.add(row["syllabus_id"])
            if row["source_version_id"]:
                reachable_v.add(row["source_version_id"])
        if prior == (len(reachable_s), len(reachable_v)):
            break
    if reachable_s != set(sy) or reachable_v != set(ve):
        fail()
    edges, cycles, mismatches = contract.graph(data["syllabi"], data["versions"])
    if data["edges"] != edges or data["cycles"] != cycles or data["owner_mismatches"] != mismatches:
        fail()
    return value
