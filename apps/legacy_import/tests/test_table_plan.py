import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from apps.legacy_import.services import table_plan as plan_module
from apps.legacy_import.services.table_plan import (
    EXPECTED_ROW_COUNT,
    EXPECTED_TABLE_COUNT,
    LegacyTableAction,
    LegacyTablePlanError,
    load_legacy_table_plan,
)

_EXPECTED_FINGERPRINT = "3868ca938f1134e9ee666ab066f6ac03e673414984780c016f20b587ec05e0d1"
_EXPECTED_SNAPSHOT = "177ef2269027395fd3a80fc1dd592aab565dda7cbca5f6f08785313881d68fe0"
_DOMAIN_KEYS = {
    "Akademik struktur/plan": "academic_structure",
    "Bildirişlər/kommunikasiya": "communications",
    "Canlı turnir": "live_tournament",
    "Jurnal/qiymətləndirmə": "grading",
    "Kitabxana": "library",
    "Sillabus/kurs məzmunu": "syllabus",
    "Xidməti müraciət": "service_request",
    "İmtahan": "exams",
    "Şəxsiyyət/RBAC": "identity_rbac",
}


def _mapping_report():
    repository = Path(__file__).resolve().parents[3]
    return json.loads((repository / "docs/migration/reports/LEGACY_TABLE_MAPPING_V1.json").read_text())


def test_runtime_plan_exactly_matches_canonical_non_narrative_fields():
    report_rows = _mapping_report()
    plan = load_legacy_table_plan()

    assert len(plan.entries) == EXPECTED_TABLE_COUNT == len(report_rows) == 81
    assert plan.expected_row_count == EXPECTED_ROW_COUNT == 9_044_531
    assert plan.fingerprint == _EXPECTED_FINGERPRINT
    assert plan.source_snapshot_sha256 == _EXPECTED_SNAPSHOT
    assert [entry.source_table for entry in plan.entries] == [row["old_table"] for row in report_rows]
    assert [entry.expected_rows for entry in plan.entries] == [row["exact_rows"] for row in report_rows]
    assert [entry.compatibility_pct for entry in plan.entries] == [row["compatibility_pct"] for row in report_rows]
    assert [entry.status for entry in plan.entries] == [row["status"] for row in report_rows]
    assert [entry.domain_key for entry in plan.entries] == [_DOMAIN_KEYS[row["domain"]] for row in report_rows]


def test_all_source_plan_entries_are_immutable_and_never_authorize_target_writes():
    plan = load_legacy_table_plan()

    assert all(entry.action.is_fail_closed for entry in plan.entries)
    assert all(entry.action.authorizes_target_write is False for entry in plan.entries)
    assert all(entry.adapter_key is None for entry in plan.entries)
    assert all(not hasattr(entry, field) for entry in plan.entries for field in ("problem", "method", "new_target"))

    with pytest.raises(FrozenInstanceError):
        plan.entries[0].expected_rows = 0


def test_syllabus_archive_security_unknown_and_empty_dispositions_are_explicitly_gated():
    plan = load_legacy_table_plan()
    syllabus = [entry for entry in plan.entries if entry.domain_key == "syllabus"]

    assert len(syllabus) == 12
    assert {entry.action for entry in syllabus} == {LegacyTableAction.DESIGN_GATED}
    assert plan.entry_for("students_telegram").action is LegacyTableAction.SECURITY_GATED
    assert plan.entry_for("workers_permits").action is LegacyTableAction.SECURITY_GATED
    assert plan.entry_for("ntg").action is LegacyTableAction.UNKNOWN_GATED
    assert plan.entry_for("curricula_tam").action is LegacyTableAction.ARCHIVE_GATED
    assert plan.entry_for("books").action is LegacyTableAction.EMPTY_GATED
    assert plan.entry_for("exam_answers").action is LegacyTableAction.TRANSFORM_CANDIDATE
    assert plan.entry_for("exam_answers").authorizes_target_write is False


def test_loader_is_cwd_independent_and_rejects_unregistered_or_unsafe_names(tmp_path, monkeypatch):
    plan_module.load_legacy_table_plan.cache_clear()
    monkeypatch.chdir(tmp_path)
    plan = load_legacy_table_plan()

    assert plan.fingerprint == _EXPECTED_FINGERPRINT
    for value in ("missing_table", "students;DROP TABLE", "", None, 1):
        with pytest.raises(LegacyTablePlanError):
            plan.entry_for(value)


def test_fail_closed_status_cannot_be_relabelled_as_transform_candidate(monkeypatch):
    rows = list(plan_module._PLAN_ROWS)
    index = next(index for index, row in enumerate(rows) if row[0] == "students_telegram")
    name, count, compatibility, status, _action, domain = rows[index]
    rows[index] = (name, count, compatibility, status, "transform_candidate", domain)
    monkeypatch.setattr(plan_module, "_PLAN_ROWS", tuple(rows))

    with pytest.raises(LegacyTablePlanError) as exc_info:
        plan_module._validated_entries()

    assert exc_info.value.code == "legacy_table_plan_fail_closed_action_invalid"
