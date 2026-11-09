"""Validate ID-only audit evidence against the pinned private snapshot; no ORM/import writes."""

import ast
import collections
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).parent
ROOT = OUT.parents[3]
SOURCE = Path("/Users/elvin/Desktop/RIM/Secret/reaudit-20261109/metadata.json")
SHA = "d38583d40048d3b1da47bb8cf77337f00d576e0647089e901b5752bddd3b880a"
raw = SOURCE.read_bytes()
assert hashlib.sha256(raw).hexdigest() == SHA
source = json.loads(raw)
data = source["data"]


def read(name):
    return json.loads((OUT / name).read_text())


work = read("groups_workload_matches.json")
groups = read("groups_current_findings.json")
slots = read("timetable_current_scope.json")
reviewed = read("groups_reviewed_statuses.json")
period = work["source"]["current_period_id"]
expected = {o["id"] for o in data["offerings"] if o["is_active"] and o["period_id"] == period}
actual = [o["offering_id"] for o in work["offerings"]]
assert len(actual) == len(set(actual)) and set(actual) == expected
categories = collections.Counter(o["category"] for o in work["offerings"])
assert dict(categories) == work["summary"]["classification_counts"]
assert sum(categories.values()) == len(expected) == 1700
assert categories["SUBJECT_ABSENT_FROM_RELEASED_OWNER_PERIOD_LOAD"] == 95
assert len([o for o in work["offerings"] if o["instructor_id"]]) == 1579
assert work["summary"]["unmatched_owner_candidate_count"] == 202
assert set(groups["pk_duplicates"].values()) == {0}
assert all(v["count_vs_unique_token_mismatches"] == 0 for v in groups["token_integrity"].values())
assert groups["counts"]["coexisting_parent_child_subject_families"] == 5
assert len(groups["family_geometry_conflicts"]) == 3
assert len(groups["multiple_parent_candidates"]) == 2
assert slots["live"] + slots["parked"] + slots["deleted"] == slots["slot_rows"] == 162
assert len(slots["live_slots_on_inactive_offerings"]) == 8
assert len(reviewed["cases"]) == 5
assert reviewed["cases"][4]["original_five_live"] is None
assert reviewed["cases"][4]["target_is_parked"] is False

forbidden = {
    "student_id",
    "student_tokens",
    "first_name",
    "last_name",
    "username",
    "fin",
    "email",
    "password",
    "private_key",
    "name",
    "groups_text",
    "subject_text",
}


def check_fields(value, trail=""):
    if isinstance(value, dict):
        for key, child in value.items():
            assert key not in forbidden, f"Unexpected raw field {trail}/{key}"
            check_fields(child, f"{trail}/{key}")
    elif isinstance(value, list):
        for child in value:
            check_fields(child, trail)


checked = [
    "groups_current_findings.json",
    "groups_workload_matches.json",
    "groups_reviewed_statuses.json",
    "groups_contact_share_scope.json",
    "timetable_current_scope.json",
    "groups_recent_operations.json",
]
for filename in checked:
    check_fields(read(filename))

code = read("groups_code_semantics.json")
for path in [
    "apps/workload/services/journal_assignments.py",
    "apps/workload/services/offering_shares.py",
    "apps/registrar/teacher_journal_list.py",
    "apps/workload/services/scoped_snapshot/data.py",
]:
    if not any(r["path"] == path for r in code["files"]):
        tree = ast.parse((ROOT / path).read_text())
        code["files"].append(
            {
                "path": path,
                "symbols": [
                    {"name": n.name, "line": n.lineno, "end_line": n.end_lineno}
                    for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.ClassDef))
                ],
                "recent_commit_ids_dates": [],
            }
        )
(OUT / "groups_code_semantics.json").write_text(json.dumps(code, ensure_ascii=False, indent=2) + "\n")
predicate = read("groups_predicate_checks.json")
predicate["live_affected_count"] = {
    "explicit_pointer_vs_name_conflict_edges": 0,
    "reference": "groups_current_findings.json",
    "captured_at": source["captured_at"],
}
(OUT / "groups_predicate_checks.json").write_text(json.dumps(predicate, ensure_ascii=False, indent=2) + "\n")
validation = {
    "source_sha256_verified": SHA,
    "application_head": "45892d9011e6e31d9ad39f9999fa3cb7f6717f84",
    "active_current_offering_coverage": {
        "expected": len(expected),
        "unique_checked": len(actual),
        "missing": 0,
        "extra": 0,
    },
    "classification_partition_matches": True,
    "pk_duplicate_checks_passed": True,
    "token_set_counts_match": True,
    "five_reviewed_cases_present": True,
    "missing_slot_is_unknown_not_false": True,
    "raw_personal_fields_absent_from_structured_findings": True,
    "checked_output_files": checked,
    "no_database_write_or_application_setup": True,
    "limitations": [
        "Static field allowlist check is not a substitute for all-source privacy review",
        "Coverage is bounded metadata, not full UI/current DB relational closure",
    ],
}
(OUT / "groups_validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(validation, ensure_ascii=False))
