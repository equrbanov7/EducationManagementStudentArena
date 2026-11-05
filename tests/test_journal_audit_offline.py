"""Synthetic regression checks: audit candidates must never become false QB facts."""

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts/prod_ops" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


checks = module("journal_audit_checks")
cells = module("journal_audit_live_cells")
syllabus = module("journal_audit_syllabus")


def sample():
    offerings = [{"id": oid, "subject_id": "s", "period_id": "p"} for oid in ("o1", "o2")]
    enrollments = [
        {
            "id": f"e{n}",
            "offering_id": f"o{n}",
            "student_id": 5,
            "status": "enrolled",
            "superseded_by_id": None,
            "absence_hours": 2,
        }
        for n in (1, 2)
    ]
    lessons = [
        {
            "id": f"l{n}",
            "offering_id": f"o{n}",
            "date": "2026-10-01",
            "start_time": "08:30:00",
            "kind": "lecture",
            "hours": 2,
            "topic": "Network",
        }
        for n in (1, 2)
    ]
    marks = [{"id": f"m{n}", "lesson_id": f"l{n}", "enrollment_id": f"e{n}", "status": "absent"} for n in (1, 2)]
    payload = {
        "batch": "one",
        "captured_at": "2026-11-04T10:00:00Z",
        "data": {"offerings": offerings, "enrollments": enrollments, "lessons": lessons, "marks": marks},
    }
    inventory = {"inventory": [{"offering_id": oid, "subject": "Kompüter şəbəkələri"} for oid in ("o1", "o2")]}
    return payload, inventory


def test_parallel_absence_is_a_candidate_not_confirmed_wrong_qb():
    payload, inventory = sample()
    result = cells.inspect([payload], inventory)
    assert result["issue_counts"] == {"parallel_active_enrollments": 1, "repeated_absence_same_slot": 1}
    assert result["issues"]["repeated_absence_same_slot"][0]["confirmed_wrong_qb"] is False
    assert result["credits_and_legacy_qb_flags_available"] is False


def test_transferred_dropped_row_is_not_a_parallel_active_subject():
    payload, inventory = sample()
    first, second = payload["data"]["enrollments"]
    first.update(status="dropped", superseded_by_id="e2")
    second["absence_hours"] = 4
    result = cells.inspect([payload], inventory)
    assert result["issue_counts"] == {}


def test_student_surface_includes_suspended_and_inactive_without_calling_them_active():
    payload, inventory = sample()
    inventory["student_inventory"] = deepcopy(inventory["inventory"])
    inventory["student_inventory"][1]["is_active"] = False
    inventory["inventory"] = inventory["inventory"][:1]
    payload["data"]["enrollments"][1]["status"] = "suspended"
    assert cells.inspect([payload], inventory)["issue_counts"] == {}
    result = cells.inspect([payload], inventory, student_surface=True)
    assert result["issue_counts"]["parallel_nondropped_enrollments"] == 1
    assert result["issues"]["parallel_nondropped_enrollments"][0]["enrollment_statuses"] == ["enrolled", "suspended"]


def test_transfer_never_carries_another_subject_absence():
    payload, inventory = sample()
    payload["data"]["enrollments"][0].update(status="dropped", superseded_by_id="e2")
    payload["data"]["offerings"][0]["subject_id"] = "different"
    result = cells.inspect([payload], inventory)
    assert result["issue_counts"] == {}


def test_lower_cached_hours_cannot_be_called_error_without_credit_ledger():
    payload, inventory = sample()
    payload["data"]["enrollments"][0]["absence_hours"] = 0
    result = cells.inspect([payload], inventory)
    candidate = result["issues"]["cached_below_raw_requires_credit_check"][0]
    assert candidate["raw_upper_bound"] == 2
    assert candidate["confirmed_wrong_qb"] is False


def test_latest_capture_preserves_deletion_instead_of_resurrecting_old_mark():
    payload, inventory = sample()
    newer = deepcopy(payload)
    newer.update(batch="two", captured_at="2026-11-04T11:00:00Z")
    newer["data"]["marks"] = []
    for row in newer["data"]["enrollments"]:
        row["absence_hours"] = 0
    result = cells.inspect([newer, payload], inventory)
    assert result["counts"]["all_captured_marks"] == 0
    assert "repeated_absence_same_slot" not in result["issues"]


def test_fixed_parts_with_same_parent_are_not_overwritten():
    payload, inventory = sample()
    one, two = deepcopy(payload), deepcopy(payload)
    one["part"], two["part"] = "one-part-001", "one-part-002"
    for table in one["data"]:
        one["data"][table] = one["data"][table][:1]
        two["data"][table] = two["data"][table][1:]
    result = cells.inspect([one, two], inventory)
    assert result["counts"]["all_captured_marks"] == 2
    assert result["counts"]["captured_current_journals"] == 2


def test_different_times_and_different_kinds_are_not_duplicate_sessions():
    payload, inventory = sample()
    payload["data"]["lessons"][1]["start_time"] = "10:00:00"
    result = cells.inspect([payload], inventory)
    assert "repeated_absence_same_slot" not in result["issues"]
    payload["data"]["lessons"][1].update(start_time="08:30:00", kind="seminar")
    assert "repeated_absence_same_slot" not in cells.inspect([payload], inventory)["issues"]


def test_present_and_absent_collision_is_separately_reported():
    payload, inventory = sample()
    payload["data"]["marks"][1]["status"] = "present"
    payload["data"]["enrollments"][1]["absence_hours"] = 0
    result = cells.inspect([payload], inventory)
    assert result["issues"]["conflicting_attendance_same_slot"][0]["statuses"] == ["absent", "present"]


def test_blank_time_never_implies_simultaneous_absence():
    payload, inventory = sample()
    for lesson in payload["data"]["lessons"]:
        lesson["start_time"] = None
    result = cells.inspect([payload], inventory)
    assert "repeated_absence_same_slot" not in result["issues"]


def test_name_normalization_keeps_subject_numbers_and_levels():
    assert checks.normalize("İKT — 1") == checks.normalize("ikt-1")
    assert checks.normalize("İKT 1") != checks.normalize("İKT 2")
    assert checks.normalize("English Beginner") != checks.normalize("English Intermediate")
    assert checks.normalize("C++") != checks.normalize("C")
    assert checks.normalize("C#") != checks.normalize("C")


def syllabus_sample():
    body = {"week": {"rows": [{"topic": "Maliyyə auditi", "lecture": 2}]}}
    baseline = {"syllabus.SyllabusSection": [{"version_id": "v", "section_id": "week", "data": body["week"]}]}
    version = {
        "id": "v",
        "canonical_policy": "exact_syllabus_recovery.digest/1",
        "canonical_body_sha256": syllabus.digest(body),
        "topic_summary": {"nonempty_topic_count": 1, "hours_without_topic_count": 0},
        "plan_hours": {"valid": True, "hours": {"lecture": 2, "seminar": 0, "lab": 0, "practical": 0}},
    }
    payload = {
        "batch": "one",
        "captured_at": "2026-11-04T10:00:00Z",
        "data": {
            "roots": [
                {
                    "offering_id": "o",
                    "effective_approved_version_id": "v",
                    "selected_syllabus_id": "s",
                    "relation": "own",
                }
            ],
            "versions": [version],
            "syllabi": [{"id": "s", "subject_id": "subject"}],
            "sections": [{"version_id": "v", "section_id": "week", "raw_data_sha256": syllabus.digest(body["week"])}],
        },
    }
    inventory = {
        "inventory": [{"offering_id": "o", "subject": "Maliyyə auditi", "subject_id": "subject", "lesson_hours": 2}]
    }
    return payload, baseline, inventory


def test_identical_uuid_is_not_proof_of_current_syllabus_content():
    payload, baseline, inventory = syllabus_sample()
    payload["data"]["versions"][0]["canonical_body_sha256"] = "changed"
    payload["data"]["sections"][0]["raw_data_sha256"] = "changed"
    row = syllabus.inspect([payload], baseline, inventory)["inventory"][0]
    assert row["body_evidence"] == "fresh_fingerprint_only"
    assert "topics" not in row


def test_exact_current_hash_makes_old_body_inspectable_but_not_semantically_certified():
    payload, baseline, inventory = syllabus_sample()
    row = syllabus.inspect([payload], baseline, inventory)["inventory"][0]
    assert row["body_evidence"] == "full_body_exact_hash_verified"
    assert row["topics"] == ["Maliyyə auditi"]
    assert row["semantic_review"] == "not_manually_certified"


def test_weekly_hours_are_compared_with_version_plan_as_separate_evidence():
    payload, baseline, inventory = syllabus_sample()
    payload["data"]["versions"][0]["topic_summary"].update(
        totals_complete=True, hours_by_kind={"lecture": 1, "seminar": 0, "practical": 0, "lab": 0}
    )
    result = syllabus.inspect([payload], baseline, inventory)
    row = result["issues"]["weekly_total_differs_from_version_plan"][0]
    assert (row["weekly_total"], row["plan_total"]) == (1, 2)
    assert "journal_syllabus_hours_difference" not in result["issues"]


def test_exact_body_hash_does_not_clear_a_forensic_lineage_cycle():
    payload, baseline, inventory = syllabus_sample()
    payload["data"]["held_roots"] = [{"offering_id": "o", "lineage_cycle_affected": True}]
    result = syllabus.inspect([payload], baseline, inventory)
    row = result["inventory"][0]
    assert row["body_evidence"] == "full_body_exact_hash_verified"
    assert row["lineage_cycle_affected"] is True
    assert result["issues"]["lineage_cycle_affected"][0]["offering_id"] == "o"
    payload["data"]["held_roots"][0]["lineage_cycle_affected"] = False
    assert "lineage_cycle_affected" not in syllabus.inspect([payload], baseline, inventory)["issues"]
