"""Phase ``journal_components`` (J5) testləri: k1-k3 + si → komponent balları."""

from decimal import Decimal

from django.apps import apps as django_apps

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
)
from apps.legacy_import.services.rehearsal_journal_components_phase import (
    COMPONENT_PLANS,
    COMPONENTS_ENTITY_TYPE,
    DERIVED_DIGEST_NAMESPACE,
    ISSUE_SEVERITY,
    JOURNAL_COMPONENTS_PHASE_KEY,
    JournalComponentsPhase,
    classify_component_cell,
)
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db


def test_the_phase_declares_a_batch_less_journal_keyed_shape(db):
    phase = JournalComponentsPhase()

    assert phase.phase_key == JOURNAL_COMPONENTS_PHASE_KEY and phase.order == 42
    assert phase.source_tables == () and phase.entity_types == (COMPONENTS_ENTITY_TYPE,)
    assert phase.declared_source_rows(harness.plan(harness.tables())) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_ledger_sort_key is str
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "journal_components_materialised"


def test_issue_severity_map_covers_exactly_the_component_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_journal_component_code_unknown": "warning",
        "legacy_journal_component_score_out_of_range": "warning",
        "legacy_journal_component_enrollment_unresolved": "warning",
        "legacy_journal_component_target_conflict": "warning",
        "legacy_journal_component_orphan": "info",
        "legacy_journal_component_duplicate": "info",
        "legacy_journal_component_empty": "info",
        "legacy_journal_component_archive_overlap": "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)


def test_the_component_plan_mirrors_journal_extras():
    """Ad/kind/tavan ``journal_extras`` ilə EYNİ olmalıdır — servis ADLA mənimsəyir."""

    assert COMPONENT_PLANS["k1"][:3] == ("Kollokvium 1", "kollokvium", 10)
    assert COMPONENT_PLANS["k2"][:3] == ("Kollokvium 2", "kollokvium", 10)
    assert COMPONENT_PLANS["k3"][:3] == ("Kollokvium 3", "kollokvium", 10)
    assert COMPONENT_PLANS["si"][:3] == ("Sərbəst iş", "self_work", 10)


@pytest.mark.parametrize(
    "point, expected",
    [
        ("0", ("scored", Decimal(0))),
        ("10", ("scored", Decimal(10))),
        ("", ("empty", None)),
        ("11", ("range", None)),
        # Canlı mənbədə k*/si xanalarında davamiyyət kodları da var — bal deyil.
        ("qb", ("unknown", None)),
        ("ie", ("unknown", None)),
        ("l", ("unknown", None)),
    ],
)
def test_classify_component_cell_is_strict(point, expected):
    assert classify_component_cell(point) == expected


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        JournalComponentsPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


def test_the_dependency_gate_is_evidence_not_config():
    rows = harness.tables()
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalComponentsPhase().run(harness.context(rows_by_table=rows, phase_keys=("journal_components",)))

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="journal_components_actor", email="jc-actor@example.test", password="test-only"
    )


def _scores(org):
    return django_apps.get_model("registrar", "ComponentScore").objects.filter(organization=org)


def _components(org):
    return django_apps.get_model("registrar", "AssessmentComponent").objects.filter(organization=org)


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=COMPONENTS_ENTITY_TYPE)
    }


def _run_phase(actor, slug, rows, *, notes=None, org=None, run=None, seed=True):
    org = org or harness.organization(actor, slug)
    run = run or harness.running_run(org, actor, table_plan=harness.plan(rows))
    if seed:
        harness.seed_journal_target(org, actor, run.pk)
    report = JournalComponentsPhase().run(
        harness.context(rows_by_table=rows, run=run, organization=org, actor=actor, notes=notes)
    )
    return org, run, report


def _component_cell(legacy_pk, month_id, point, **overrides):
    return harness.point_row(legacy_pk, month_id=month_id, day_number=month_id, point=point, **overrides)


def test_the_happy_path_creates_all_four_components(actor):
    rows = harness.tables(
        points=[
            _component_cell(1, "k1", "8"),
            _component_cell(2, "k2", "7"),
            _component_cell(3, "k3", "10"),
            _component_cell(4, "si", "5"),
        ]
    )
    notes = []
    org, run, report = _run_phase(actor, "components-happy", rows, notes=notes)

    assert dict(report.state_counts) == {"journal_components_materialised": 1}
    assert sorted(_components(org).values_list("name", "kind", "max_score")) == [
        ("Kollokvium 1", "kollokvium", 10),
        ("Kollokvium 2", "kollokvium", 10),
        ("Kollokvium 3", "kollokvium", 10),
        ("Sərbəst iş", "self_work", 10),
    ]
    assert sorted(str(score) for score in _scores(org).values_list("score", flat=True)) == [
        "10.00",
        "5.00",
        "7.00",
        "8.00",
    ]
    assert _issues(run) == {}
    assert notes == [f"{JOURNAL_COMPONENTS_PHASE_KEY}.records.1"]


def test_an_empty_cell_writes_nothing_and_only_reports(actor):
    rows = harness.tables(points=[_component_cell(1, "k1", "")])
    org, run, report = _run_phase(actor, "components-empty", rows)

    assert dict(report.state_counts) == {"journal_components_skipped": 1}
    assert _scores(org).count() == 0 and _components(org).count() == 0
    assert _issues(run) == {(harness.UNIQID, "legacy_journal_component_empty"): "info"}


def test_out_of_range_and_attendance_codes_are_quarantined(actor):
    rows = harness.tables(
        points=[
            _component_cell(1, "k1", "11"),
            _component_cell(2, "k2", "qb"),
        ]
    )
    org, run, report = _run_phase(actor, "components-quarantine", rows)

    assert dict(report.state_counts) == {"journal_components_unresolved": 1}
    assert _scores(org).count() == 0
    assert _issues(run) == {
        (harness.UNIQID, "legacy_journal_component_score_out_of_range"): "warning",
        (harness.UNIQID, "legacy_journal_component_code_unknown"): "warning",
    }


def test_the_duplicate_winner_is_the_highest_update_counter(actor):
    rows = harness.tables(
        points=[
            _component_cell(1, "k1", "3", update_counter=0),
            _component_cell(2, "k1", "9", update_counter=5),
        ]
    )
    org, run, _report = _run_phase(actor, "components-duplicate", rows)

    assert _scores(org).get().score == Decimal("9.00")
    assert _issues(run) == {(harness.UNIQID, "legacy_journal_component_duplicate"): "info"}


def test_an_unmigrated_journal_is_an_orphan(actor):
    rows = harness.tables(
        journals=[harness.journal_row(2, harness.UNIQID), harness.journal_row(3, "fakeAAAAAA", fake=1)],
        points=[_component_cell(1, "k1", "8", uniqid="fakeAAAAAA")],
    )
    org, run, report = _run_phase(actor, "components-orphan", rows)

    assert dict(report.state_counts) == {"journal_components_skipped": 1}
    assert _issues(run) == {("fakeAAAAAA", "legacy_journal_component_orphan"): "info"}
    assert _scores(org).count() == 0


def test_the_archive_cutoff_applies_to_component_cells(actor):
    rows = harness.tables(
        archive=[
            _component_cell(1, "k1", "6", added_date=harness.BEFORE_CUTOFF),
            _component_cell(2, "k2", "4", added_date=harness.AFTER_CUTOFF),
        ]
    )
    org, run, _report = _run_phase(actor, "components-archive", rows)

    assert [str(score) for score in _scores(org).values_list("score", flat=True)] == ["6.00"]
    assert (harness.UNIQID, "legacy_journal_component_archive_overlap") in _issues(run)


def test_a_repeated_invocation_replays_the_sealed_journal(actor):
    rows = harness.tables(points=[_component_cell(1, "k1", "8"), _component_cell(2, "k2", "qb")])
    org, run, first = _run_phase(actor, "components-replay", rows)
    second = JournalComponentsPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert _scores(org).count() == 1


def test_the_live_phase_digest_equals_the_ledger_rebuild(actor):
    rows = harness.tables(
        journals=[harness.journal_row(2, harness.UNIQID), harness.journal_row(3, "fakeAAAAAA", fake=1)],
        points=[
            _component_cell(1, "k1", "8"),
            _component_cell(2, "k2", "11"),
            _component_cell(3, "si", "4", uniqid="fakeAAAAAA"),
        ],
    )
    _org, run, live = _run_phase(actor, "components-rebuild", rows)
    rebuilt = phase_report_from_ledger(run, phase=JournalComponentsPhase(), plan=harness.plan(rows))

    assert rebuilt.phase_digest == live.phase_digest
    assert dict(rebuilt.state_counts) == dict(live.state_counts)
