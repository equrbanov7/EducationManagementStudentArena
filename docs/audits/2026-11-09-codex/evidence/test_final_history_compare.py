"""Offline synthetic final comparisons; no database or real source values."""

import copy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "final_history_compare", Path(__file__).with_name("final_history_compare.py")
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def row(identifier, **fields):
    return {"id": identifier, "organization_id": module.ORG, **fields}


def mapping(identifier, entity, legacy, label, target):
    return row(
        identifier,
        source_system=module.SYSTEM,
        entity_type=entity,
        legacy_pk=legacy,
        target_model_label=label,
        target_pk=target,
        state="migrated",
        source_row_hash="a" * 64,
        transform_version="v1",
        reconciliation_status="matched",
        created_run_id="run1",
    )


@pytest.fixture
def inputs():
    tables = {key: [] for key in module.REQUIRED}
    tables["organizations.AcademicPeriod"] = [row("period")]
    tables["registrar.CourseOffering"] = [row("course", period_id="period", subject_id="subject")]
    tables["registrar.Enrollment"] = [row("enrollment", offering_id="course", student_id="student")]
    tables["registrar.FinalGrade"] = [row("grade", enrollment_id="enrollment", exam_score="0", entered_by_id=None)]
    tables["legacy_import.LegacyEntityMap"] = [
        mapping("m1", "journal_enrollment", "journal:7", "registrar.enrollment", "enrollment"),
        mapping("m2", "student", "7", "auth.user", "student"),
        mapping("m3", "lesson_subject", "9", "registrar.subject", "subject"),
        mapping("m4", "academic_period", "11", "organizations.academicperiod", "period"),
    ]
    point = dict(
        id=1,
        journal_uniqid="journal",
        student_id=7,
        month_id="im",
        day_number="1",
        time="9:00:00",
        point="0",
        update_counter=1,
        updated_at="2026-01-01 00:00:00",
    )
    source = {
        "journals": [dict(id=3, uniqid="journal", semestr=11, lesson_id=9, fake=0, sonra_sil=0)],
        "points": {"journals_dates_points": [point], "journals_dates_points_archive": []},
    }
    selected = {
        "rows": [
            dict(table="journals_dates_points", source_id=1, source_student_id=7, journal_uniqid="journal", kind="im")
        ]
    }
    return {"tables": tables}, source, selected


def result(inputs):
    current, source, selected = inputs
    return module.Comparison(current, source, selected).result(source, {})


def test_zero_and_exact_route_are_not_missing(inputs):
    report = result(inputs)
    target = report["target_rows"][0]
    assert target["status"] == "source_current_equal" and target["source_zero"]
    assert report["summary"]["source_sem14_im_im2_rows"] == 0
    assert not target["eligible_for_apply"] and not report["all_academic_results_verified"]
    assert not {"score", "source_score", "current_score", "username", "fin"} & target.keys()


def test_native_winner_uses_update_sequence_not_maximum(inputs):
    current, source, selected = inputs
    lower = source["points"]["journals_dates_points"][0]
    source["points"]["journals_dates_points"].append({**lower, "id": 2, "point": "9", "update_counter": 0})
    assert result(inputs)["target_rows"][0]["source_zero"]
    selected["rows"][0]["source_id"] = 2
    with pytest.raises(ValueError, match="native_selection_changed"):
        result(inputs)


@pytest.mark.parametrize("kind", ["appeal", "correction"])
def test_official_current_increase_is_protected(inputs, kind):
    tables = inputs[0]["tables"]
    tables["registrar.FinalGrade"][0]["exam_score"] = "1"
    tables["registrar.ExamScoreEntry"] = [
        row(
            "entry",
            enrollment_id="enrollment",
            assessment="final",
            kind=kind,
            new_score="1",
            created_at="2026-11-01T00:00:00Z",
        )
    ]
    assert result(inputs)["target_rows"][0]["status"] == "protected_current_official_entry"


def test_missing_route_is_coverage_unknown_not_lost_grade(inputs):
    inputs[0]["tables"]["legacy_import.LegacyEntityMap"] = inputs[0]["tables"]["legacy_import.LegacyEntityMap"][1:]
    report = result(inputs)
    assert report["summary"]["source_route_counts"] == {"enrollment_route_missing": 1}
    assert report["current_without_source"][0]["status"] == "no_exact_native_source_route"
    assert not report["target_rows"]


def test_source_equal_does_not_hide_unapplied_official_increase(inputs):
    inputs[0]["tables"]["registrar.ExamScoreEntry"] = [
        row(
            "entry",
            enrollment_id="enrollment",
            assessment="final",
            kind="appeal",
            new_score="1",
            created_at="2026-11-01T00:00:00Z",
        )
    ]
    assert result(inputs)["target_rows"][0]["status"] == "current_differs_latest_official_entry_hold"
    inputs[0]["tables"]["legacy_import.LegacyEntityMap"] = inputs[0]["tables"]["legacy_import.LegacyEntityMap"][1:]
    assert (
        result(inputs)["current_without_source"][0]["official_entry_status"]
        == "current_differs_latest_official_entry_hold"
    )


def test_tied_official_entries_do_not_choose_by_uuid(inputs):
    inputs[0]["tables"]["registrar.ExamScoreEntry"] = [
        row(
            "entry1",
            enrollment_id="enrollment",
            assessment="final",
            kind="appeal",
            new_score="1",
            created_at="2026-11-01T00:00:00Z",
        ),
        row(
            "entry2",
            enrollment_id="enrollment",
            assessment="final",
            kind="correction",
            new_score="0",
            created_at="2026-11-01T00:00:00Z",
        ),
    ]
    assert result(inputs)["target_rows"][0]["status"] == "official_entry_order_ambiguous_hold"


def test_paper_entry_without_final_row_or_source_still_appears(inputs):
    tables = inputs[0]["tables"]
    tables["legacy_import.LegacyEntityMap"] = tables["legacy_import.LegacyEntityMap"][1:]
    tables["registrar.FinalGrade"] = []
    tables["registrar.ExamScoreEntry"] = [
        row(
            "entry",
            enrollment_id="enrollment",
            assessment="final",
            kind="appeal",
            new_score="1",
            created_at="2026-11-01T00:00:00Z",
        )
    ]
    report = result(inputs)
    assert report["current_without_source"][0]["official_entry_status"] == "current_differs_latest_official_entry_hold"
    assert report["summary"]["historical_enrollments_or_missing_course"] == 1
    assert report["historical_enrollment_coverage"][0]["official_final_entry_present"]


def test_period_map_required_and_foreign_tenant_rejected(inputs):
    inputs[0]["tables"]["legacy_import.LegacyEntityMap"].pop()
    assert result(inputs)["source_rows"][0]["route_status"] == "period_mapping_missing"
    inputs[0]["tables"]["registrar.FinalGrade"][0]["organization_id"] = "foreign"
    with pytest.raises(ValueError, match="foreign_tenant"):
        result(inputs)


def test_reviewed_correction_not_overwritten(inputs):
    tables = inputs[0]["tables"]
    tables["registrar.FinalGrade"][0]["exam_score"] = "1"
    tables["registrar.LegacyGradeFact"] = [
        row(
            "fact",
            source_system=module.SYSTEM,
            source_table="journals_dates_points",
            source_pk=1,
            enrollment_id="enrollment",
        )
    ]
    tables["registrar.LegacyGradeReview"] = [
        row(
            "review",
            fact_id="fact",
            decision="verified",
            reason_code="exam_center_corrected",
            created_at="2026-11-01T00:00:00Z",
        )
    ]
    assert result(inputs)["target_rows"][0]["status"] == "reviewed_correction_preserve_current_hold"


def test_latest_applied_map_version_replaces_old_target(inputs):
    tables = inputs[0]["tables"]
    base = tables["legacy_import.LegacyEntityMap"][0]
    base["target_pk"] = "old-enrollment"
    initial = row(
        "v1",
        entity_map_id=base["id"],
        version_number=1,
        recorded_run_id="run1",
        supersedes_id=None,
        **{k: base[k] for k in module.effective_maps.__globals__["FIELDS"]},
    )
    revised = {
        **initial,
        "id": "v2",
        "version_number": 2,
        "target_pk": "enrollment",
        "supersedes_id": "v1",
        "approved_issue_id": "issue",
        "reviewed_by_id": 1,
        "reviewed_at": "2026-11-01T00:00:00Z",
        "review_reason_code": "reviewed",
        "review_evidence_digest": "b" * 64,
        "applied_by_id": 1,
    }
    tables["legacy_import.LegacyEntityMapVersion"] = [initial, revised]
    assert result(inputs)["target_rows"][0]["status"] == "source_current_equal"
    tables["legacy_import.LegacyEntityMapVersion"][-1] = {**revised, "applied_by_id": None}
    with pytest.raises(ValueError, match="unapplied_or_unreviewed"):
        result(inputs)


def test_conflicting_sources_never_select_highest(inputs):
    current, source, selected = inputs
    second = copy.deepcopy(source["points"]["journals_dates_points"][0])
    second.update(id=2, day_number="2", point="9")
    source["points"]["journals_dates_points"].append(second)
    selected["rows"].append({**selected["rows"][0], "source_id": 2})
    assert result(inputs)["target_rows"][0]["status"] == "conflicting_canonical_source_values_hold"


def test_resit_stays_separate_from_paper_final(inputs):
    tables = inputs[0]["tables"]
    inputs[1]["points"]["journals_dates_points"][0]["month_id"] = "im2"
    inputs[2]["rows"][0]["kind"] = "im2"
    tables["registrar.ResitRecord"] = [row("resit", enrollment_id="enrollment", resit_score="0", status="completed")]
    assert result(inputs)["target_rows"][0]["status"] == "source_current_equal"
    tables["registrar.ResitRecord"][0]["status"] = "eligible"
    assert result(inputs)["target_rows"][0]["status"] == "resit_status_score_conflict_hold"
