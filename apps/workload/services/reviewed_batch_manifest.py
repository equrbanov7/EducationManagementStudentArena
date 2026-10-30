"""Strict, data-only contract for reviewed chair source batches.

No imports, teacher discovery, fuzzy matching or executable expressions come
from the supplied file. Its SHA and explicit source-line selection are required.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path

from .sbio235_state import RepairError, digest
from .task_form1_parsing import hours_value

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
YEAR = "2026/2027"
RESOURCE = "workload.reviewed_source_batch"
ACTIVITIES = ("lecture", "seminar", "lab")
ALLOWED_CLASSES = {
    "existing_course_patch_owner_preserved": "patch",
    "existing_owner_no_load": "restore",
    "literal_or_spelling_unique_existing_membership_newrow": "create",
    "older_catalogue_fk_current_preflight_needed": "create",
    "reviewed_catalogue_alias": "create",
    "reviewed_catalogue_new_exact": "create",
    "reviewed_handover_existing_row": "patch",
    "reviewed_handover_missing_row": "restore",
}
FORMS = {"full_time": "eyani", "part_time": "qiyabi", "eyani": "eyani", "qiyabi": "qiyabi"}


def uid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise RepairError("manifest_uuid_invalid") from exc


def integer(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, int) or value < int(positive):
        raise RepairError("manifest_integer_invalid")
    return value


def geometry(value):
    """Strict integer literal, equal sum or product; keep unit and total apart."""
    text = str(value or "").strip()
    if not text or set(text) <= {"-", "–", "—", " "}:
        return {"unit": 0, "total": 0, "count": 1}
    if not re.fullmatch(r"\d+(?:\s*(?:[xX*×]|\+)\s*\d+)*", text):
        raise RepairError("source_hour_expression_invalid")
    normalized = text.replace("×", "*").lower().replace("x", "*")
    if "*" in normalized and "+" in normalized:
        raise RepairError("mixed_hour_expression_not_reviewed")
    numbers = [int(value) for value in re.findall(r"\d+", normalized)]
    if "*" in normalized:
        if len(numbers) != 2:
            raise RepairError("hour_product_shape_invalid")
        unit, count = numbers
    elif "+" in normalized:
        if len(set(numbers)) != 1:
            raise RepairError("unequal_source_sections_need_explicit_review")
        unit, count = numbers[0], len(numbers)
    else:
        unit, count = numbers[0], 1
    if count < 1 or count > 20 or unit > 1500:
        raise RepairError("source_hour_range_invalid")
    total = hours_value(normalized)
    if total != unit * count:
        raise RepairError("source_hour_parser_disagreement")
    return {"unit": unit, "count": count, "total": total}


def read_manifest(path, sha256):
    if not re.fullmatch(r"[a-f0-9]{64}", sha256 or ""):
        raise RepairError("manifest_sha256_required")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(Path(path), flags), "rb") as handle:
        mode = os.fstat(handle.fileno())
        if not stat.S_ISREG(mode.st_mode) or mode.st_mode & 0o077 or mode.st_size > 10_000_000:
            raise RepairError("manifest_private_regular_file_required")
        raw = handle.read()
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise RepairError("manifest_sha256_mismatch")
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise RepairError("manifest_json_invalid") from exc
    return value


@dataclass
class Plan:
    manifest_sha: str
    chair_id: str
    items: list
    metadata_fixes: list

    @property
    def selection_sha(self):
        return digest({"manifest": self.manifest_sha, "lines": sorted(item["line"] for item in self.items)})

    @property
    def task_ids(self):
        return {item["task_id"] for item in self.items}

    @property
    def teacher_ids(self):
        return {assignment["teacher_id"] for item in self.items for assignment in item["assignments"]}

    @property
    def keys(self):
        return {(item["subject_id"], item["period_id"], gid) for item in self.items for gid in item["group_ids"]}

    @property
    def group_ids(self):
        return {gid for item in self.items for gid in item["group_ids"]} | {
            fix["group_id"] for fix in self.metadata_fixes
        }


def _item(entry, *, version="reviewed-workload-source/1"):
    from .reviewed_batch_policy import parse
    from .reviewed_source_geometry import geometry_for_entry

    mode = ALLOWED_CLASSES.get(entry.get("ready_class"))
    if mode is None or entry.get("delegated_existing_repair"):
        raise RepairError("source_line_outside_reviewed_operation_classes")
    source, desired = entry["source_reference"], entry["desired_row"]
    source_line = integer(source["line"], positive=True)
    line = integer(source.get("selection_id", source_line), positive=True)
    if not re.fullmatch(r"[a-f0-9]{64}", source.get("sha256", "")):
        raise RepairError("source_file_sha_missing")
    season = desired["season"]
    if season not in ("fall", "spring"):
        raise RepairError("source_season_invalid")
    cells = source["values"]
    hours = {kind: geometry(cells[season + "_" + kind]) for kind in ACTIVITIES}
    hours = geometry_for_entry(entry, hours, version=version)
    if {kind: value["total"] for kind, value in hours.items()} != entry["desired_contacts"]:
        raise RepairError("source_contact_total_mismatch")
    if not sum(value["total"] for value in hours.values()):
        raise RepairError("zero_teaching_source_row")
    group_ids = sorted({uid(value) for value in desired["group_ids"]})
    if not group_ids or len(group_ids) != len(desired["group_ids"]):
        raise RepairError("source_group_selection_invalid")
    sl_counts = {hours[kind]["count"] for kind in ("seminar", "lab") if hours[kind]["total"]}
    if len(sl_counts) > 1:
        raise RepairError("seminar_lab_section_geometry_conflict")
    union, subgroup = hours["lecture"]["count"], next(iter(sl_counts), 1)
    if max(union, subgroup) > len(group_ids):
        raise RepairError("source_sections_need_explicit_physical_group_targets")
    expected = []
    for assignment in entry["expected_assignments"]:
        kind = assignment["activity"]
        if kind not in ACTIVITIES or type(assignment["is_hourly_paid"]) is not bool:
            raise RepairError("source_assignment_invalid")
        expected.append(
            {
                "teacher_id": integer(assignment["teacher_id"], positive=True),
                "activity": kind,
                "hours": integer(assignment["hours"], positive=True),
                "is_hourly_paid": assignment["is_hourly_paid"],
            }
        )
    if {kind: sum(a["hours"] for a in expected if a["activity"] == kind) for kind in ACTIVITIES} != entry[
        "desired_contacts"
    ]:
        raise RepairError("source_assignment_total_mismatch")
    if len({(a["teacher_id"], a["activity"]) for a in expected}) != len(expected):
        raise RepairError("duplicate_teacher_contribution")
    # Version1 deliberately excludes handovers and multi-owner journals. A later
    # reviewed extension can add them without making a duplicate complete course.
    if len({a["teacher_id"] for a in expected}) != 1:
        raise RepairError("multi_teacher_course_requires_separate_reviewed_policy")
    subject_id = uid(entry["selected_subject_id"])
    subjects = [value for value in entry["subject_candidates"] if uid(value["id"]) == subject_id]
    if len(subjects) != 1 or not subjects[0].get("code") or not subjects[0].get("name"):
        raise RepairError("unique_exact_subject_identity_required")
    existing = entry["existing_rows"]
    if (mode == "patch" and len(existing) != 1) or (mode != "patch" and existing):
        raise RepairError("source_existing_row_shape_changed")
    item = {
        "line": line,
        "source_line": source_line,
        "mode": mode,
        "task_id": uid(desired["task_id"]),
        "subject_id": subject_id,
        "subject": subjects[0],
        "period_id": uid(desired["period_id"]),
        "season": season,
        "row_id": uid(existing[0]["id"]) if existing else None,
        "group_ids": group_ids,
        "source_groups": entry["physical_source_groups"],
        "teacher_identity": entry["teacher_identity"],
        "assignments": expected,
        "existing_rows": existing,
        "existing_journals": entry["existing_journals"],
        "plan": {kind: value["unit"] for kind, value in hours.items()},
        "totals": {kind: value["total"] for kind, value in hours.items()},
        "union_count": union,
        "subgroup_count": subgroup,
        "contacts": sum(value["unit"] for value in hours.values()),
        "row_data": desired,
        "source_sha": source["sha256"],
    }
    if mode != "patch" and (
        desired.get("education_form") not in FORMS
        or desired.get("degree_level") not in (None, "bachelor", "master", "phd")
    ):
        raise RepairError("new_row_degree_or_education_form_not_reviewed")
    item["policy"] = parse(entry, item, version=version)
    if mode == "patch" and entry["ready_class"].startswith("reviewed_handover") and "handover" not in item["policy"]:
        raise RepairError("explicit_handover_policy_required")
    return item


def _unique_physical_course_keys(items):
    physical = [(item["subject_id"], item["period_id"], gid) for item in items for gid in item["group_ids"]]
    if len(physical) != len(set(physical)):
        raise RepairError("overlapping_physical_course_targets_need_merged_review")


def select_manifest(value, *, sha256, lines):
    if (
        value.get("format")
        not in ("maliyye-full-source-verdict/1", "reviewed-workload-source/1", "reviewed-workload-source/2")
        or value.get("organization_id") != ORG
        or value.get("academic_year") != YEAR
    ):
        raise RepairError("manifest_fixed_tenant_year_format_required")
    if not lines or len(lines) != len(set(lines)) or len(lines) > 100:
        raise RepairError("explicit_unique_source_lines_required")
    wanted = {integer(line, positive=True) for line in lines}
    matches = [
        entry
        for entry in value["source_entries"]
        if entry["source_reference"].get("selection_id", entry["source_reference"]["line"]) in wanted
    ]
    if len(matches) != len(wanted):
        raise RepairError("source_line_missing_or_duplicate")
    items = sorted((_item(entry, version=value["format"]) for entry in matches), key=lambda item: item["line"])
    keys = [(item["subject_id"], item["period_id"], tuple(item["group_ids"])) for item in items]
    if len(keys) != len(set(keys)):
        raise RepairError("shared_course_contributions_must_be_reviewed_as_one_logical_row")
    _unique_physical_course_keys(items)
    used_groups = {uid(group["id"]) for entry in matches for group in entry["physical_source_groups"]}
    fixes = [fix for fix in value.get("metadata_fixes", []) if uid(fix["group_id"]) in used_groups]
    for fix in fixes:
        if fix.get("new_values") != {"sector": "en", "language_sector": "EN"} or not re.search(
            r"\bing\b", fix["group_name"], re.I
        ):
            raise RepairError("only_reviewed_english_metadata_fix_supported")
    return Plan(sha256, uid(value["chair_id"]), items, fixes)
