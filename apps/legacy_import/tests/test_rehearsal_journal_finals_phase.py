"""Phase ``journal_finals`` (J6) testləri: im/im2 + naməlum kodların karantini."""

from decimal import Decimal

from django.apps import apps as django_apps

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
)
from apps.legacy_import.services.rehearsal_journal_finals_phase import (
    DERIVED_DIGEST_NAMESPACE,
    FINALS_ENTITY_TYPE,
    ISSUE_SEVERITY,
    JOURNAL_FINALS_PHASE_KEY,
    JournalFinalsPhase,
    classify_final_cell,
    is_final_month,
)
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db


def test_the_phase_declares_a_batch_less_journal_keyed_shape(db):
    phase = JournalFinalsPhase()

    assert phase.phase_key == JOURNAL_FINALS_PHASE_KEY and phase.order == 44
    assert phase.source_tables == () and phase.entity_types == (FINALS_ENTITY_TYPE,)
    assert phase.declared_source_rows(harness.plan(harness.tables())) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_ledger_sort_key is str
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "journal_finals_materialised"


def test_issue_severity_map_covers_exactly_the_finals_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_journal_mark_code_unknown": "warning",
        "legacy_journal_final_score_out_of_range": "warning",
        "legacy_journal_final_enrollment_unresolved": "warning",
        "legacy_journal_final_target_conflict": "warning",
        "legacy_journal_final_orphan": "info",
        "legacy_journal_final_duplicate": "info",
        "legacy_journal_final_empty": "info",
        "legacy_journal_final_archive_overlap": "info",
        "legacy_journal_exam_score_above_scheme": "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)


@pytest.mark.parametrize(
    "month_id, expected",
    [
        # J6 catch-all: J4 (təqvim) və J5 (komponent) götürməyən HƏR kod.
        ("im", True),
        ("im2", True),
        ("pa", True),
        ("wr", True),
        ("ga", True),
        ("12", False),
        ("k1", False),
        ("si", False),
    ],
)
def test_the_catch_all_domain_takes_everything_j4_and_j5_leave(month_id, expected):
    assert is_final_month(month_id) is expected


@pytest.mark.parametrize(
    "month_id, point, expected",
    [
        ("im", "45", ("scored", Decimal(45))),
        # J-V2: 50-dən böyük dəyər SAXLANILIR (karantin deyil) — 100 sahə tavanıdır.
        ("im", "89", ("scored", Decimal(89))),
        ("im", "101", ("range", None)),
        ("im", "", ("empty", None)),
        ("im", "l", ("unknown", None)),
        ("im2", "30", ("scored", Decimal(30))),
        # J-V13: naməlum ``month_id`` kodu ümumiyyətlə oxunmur.
        ("pa", "7", ("unknown", None)),
        ("ga", "", ("unknown", None)),
    ],
)
def test_classify_final_cell_is_strict(month_id, point, expected):
    assert classify_final_cell(month_id, point) == expected


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        JournalFinalsPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


def test_the_dependency_gate_is_evidence_not_config():
    rows = harness.tables()
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalFinalsPhase().run(harness.context(rows_by_table=rows, phase_keys=("journal_finals",)))

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="journal_finals_actor", email="jf-actor@example.test", password="test-only"
    )


def _finals(org):
    return django_apps.get_model("registrar", "FinalGrade").objects.filter(organization=org)


def _resits(org):
    return django_apps.get_model("registrar", "ResitRecord").objects.filter(organization=org)


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=FINALS_ENTITY_TYPE)
    }


def _run_phase(actor, slug, rows, *, notes=None, org=None, run=None):
    org = org or harness.organization(actor, slug)
    run = run or harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk)
    report = JournalFinalsPhase().run(
        harness.context(rows_by_table=rows, run=run, organization=org, actor=actor, notes=notes)
    )
    return org, run, report


def _final_cell(legacy_pk, month_id, point, **overrides):
    return harness.point_row(legacy_pk, month_id=month_id, day_number=month_id, point=point, **overrides)


def test_the_happy_path_writes_the_exam_and_resit_scores(actor):
    rows = harness.tables(
        points=[
            _final_cell(1, "im", "45"),
            _final_cell(2, "im2", "30", student_id=harness.STUDENT_B),
        ]
    )
    notes = []
    org, run, report = _run_phase(actor, "finals-happy", rows, notes=notes)

    assert dict(report.state_counts) == {"journal_finals_materialised": 1}
    assert _finals(org).get().exam_score == Decimal("45.00")
    resit = _resits(org).get()
    # Mənbədə səbəb sütunu yoxdur → import defoltu; bal varsa qeyd tamamlanıb.
    assert (resit.resit_score, resit.reason, resit.status) == (Decimal("30.00"), "total", "completed")
    assert _issues(run) == {}
    assert notes == [f"{JOURNAL_FINALS_PHASE_KEY}.records.1"]


def test_an_exam_score_above_the_scheme_ceiling_is_kept_and_flagged(actor):
    """J-V2: ``set_exam_score``-un 50-yə clamp-ı QƏSDƏN güzgülənmir."""

    rows = harness.tables(points=[_final_cell(1, "im", "89")])
    org, run, report = _run_phase(actor, "finals-above", rows)

    assert dict(report.state_counts) == {"journal_finals_materialised": 1}
    assert _finals(org).get().exam_score == Decimal("89.00")
    assert _issues(run) == {(harness.UNIQID, "legacy_journal_exam_score_above_scheme"): "info"}


def test_unknown_month_codes_are_quarantined_with_the_documented_rule(actor):
    """J-V13: pa/wr/ss/ww/ll/rr/ga və ``im`` altındakı ``l`` — hamısı karantin."""

    rows = harness.tables(
        points=[
            _final_cell(1, "pa", "7"),
            _final_cell(2, "wr", "5"),
            _final_cell(3, "im", "l"),
        ]
    )
    org, run, report = _run_phase(actor, "finals-unknown", rows)

    assert dict(report.state_counts) == {"journal_finals_unresolved": 1}
    assert _finals(org).count() == 0 and _resits(org).count() == 0
    assert _issues(run) == {(harness.UNIQID, "legacy_journal_mark_code_unknown"): "warning"}


def test_an_out_of_range_final_score_is_quarantined(actor):
    rows = harness.tables(points=[_final_cell(1, "im", "101")])
    org, run, report = _run_phase(actor, "finals-range", rows)

    assert dict(report.state_counts) == {"journal_finals_unresolved": 1}
    assert _finals(org).count() == 0
    assert _issues(run) == {(harness.UNIQID, "legacy_journal_final_score_out_of_range"): "warning"}


def test_the_duplicate_winner_is_the_highest_update_counter(actor):
    rows = harness.tables(
        points=[
            _final_cell(1, "im", "20", update_counter=1),
            _final_cell(2, "im", "44", update_counter=4),
        ]
    )
    org, run, _report = _run_phase(actor, "finals-duplicate", rows)

    assert _finals(org).get().exam_score == Decimal("44.00")
    assert _issues(run) == {(harness.UNIQID, "legacy_journal_final_duplicate"): "info"}


def test_an_unresolved_enrollment_is_reported(actor):
    rows = harness.tables(points=[_final_cell(1, "im", "30", student_id=999)])
    org, run, report = _run_phase(actor, "finals-unresolved", rows)

    assert dict(report.state_counts) == {"journal_finals_skipped": 1}
    assert _finals(org).count() == 0
    assert _issues(run) == {(harness.UNIQID, "legacy_journal_final_enrollment_unresolved"): "warning"}


def test_the_archive_cutoff_applies_to_final_cells(actor):
    rows = harness.tables(
        archive=[
            _final_cell(1, "im", "33", added_date=harness.BEFORE_CUTOFF),
            _final_cell(2, "im2", "12", added_date=harness.AFTER_CUTOFF, student_id=harness.STUDENT_B),
        ]
    )
    org, run, _report = _run_phase(actor, "finals-archive", rows)

    assert _finals(org).get().exam_score == Decimal("33.00")
    assert _resits(org).count() == 0
    assert (harness.UNIQID, "legacy_journal_final_archive_overlap") in _issues(run)


def test_a_repeated_invocation_replays_the_sealed_journal(actor):
    rows = harness.tables(points=[_final_cell(1, "im", "45"), _final_cell(2, "pa", "3")])
    org, run, first = _run_phase(actor, "finals-replay", rows)
    second = JournalFinalsPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert _finals(org).count() == 1


def test_the_live_phase_digest_equals_the_ledger_rebuild(actor):
    rows = harness.tables(
        journals=[harness.journal_row(2, harness.UNIQID), harness.journal_row(3, "fakeAAAAAA", fake=1)],
        points=[
            _final_cell(1, "im", "45"),
            _final_cell(2, "ga", "1"),
            _final_cell(3, "im", "20", uniqid="fakeAAAAAA"),
        ],
    )
    _org, run, live = _run_phase(actor, "finals-rebuild", rows)
    rebuilt = phase_report_from_ledger(run, phase=JournalFinalsPhase(), plan=harness.plan(rows))

    assert rebuilt.phase_digest == live.phase_digest
    assert dict(rebuilt.state_counts) == dict(live.state_counts)
