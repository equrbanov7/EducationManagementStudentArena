"""Phase ``journal_lock`` (J7) testləri: bitmiş semestr kilidlənir, cari qalır."""

import datetime

from django.apps import apps as django_apps
from django.utils import timezone

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue
from apps.legacy_import.services.rehearsal_authorizer import ASSESSMENT_SCHEME_MODEL_LABEL
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
)
from apps.legacy_import.services.rehearsal_journal_lock_phase import (
    DERIVED_DIGEST_NAMESPACE,
    ISSUE_SEVERITY,
    JOURNAL_LOCK_PHASE_KEY,
    LOCK_ENTITY_TYPE,
    JournalLockPhase,
)
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db


def test_the_phase_declares_a_batch_less_journal_keyed_shape(db):
    phase = JournalLockPhase()

    assert phase.phase_key == JOURNAL_LOCK_PHASE_KEY and phase.order == 46
    assert phase.source_tables == () and phase.entity_types == (LOCK_ENTITY_TYPE,)
    assert phase.declared_source_rows(harness.plan(harness.tables())) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_ledger_sort_key is str
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "journal_locked"
    assert phase.derived_state_key("skipped") == "journal_left_open"


def test_issue_severity_map_covers_exactly_the_lock_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_journal_lock_period_unknown": "warning",
        "legacy_journal_lock_applied": "info",
        "legacy_journal_lock_deferred": "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        JournalLockPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


@pytest.mark.parametrize(
    "phase_keys",
    [("journal_lock",), ("journal_marks", "journal_lock"), ("journal_marks", "journal_finals", "journal_lock")],
)
def test_the_dependency_gate_requires_every_writing_phase(phase_keys):
    """Kilid YALNIZ J4-J6 tam bitəndən sonra qoyula bilər (J-V8)."""

    rows = harness.tables()
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalLockPhase().run(harness.context(rows_by_table=rows, phase_keys=phase_keys))

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="journal_lock_actor", email="jl-actor@example.test", password="test-only"
    )


def _schemes(org):
    return django_apps.get_model("registrar", "AssessmentScheme").objects.filter(organization=org)


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=LOCK_ENTITY_TYPE)
    }


def _run_phase(actor, slug, *, period_end, notes=None):
    rows = harness.tables()
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk, period_end=period_end)
    report = JournalLockPhase().run(
        harness.context(rows_by_table=rows, run=run, organization=org, actor=actor, notes=notes)
    )
    return org, run, report, rows


def test_a_finished_period_is_approved_and_published(actor):
    notes = []
    org, run, report, _rows = _run_phase(actor, "lock-finished", period_end=datetime.date(2022, 1, 31), notes=notes)

    assert dict(report.state_counts) == {"journal_locked": 1}
    scheme = _schemes(org).get()
    # CheckConstraint: publish ⟺ approved — hər iki sahə BİRGƏ yazılır.
    assert (scheme.approval_status, scheme.is_published) == ("approved", True)
    assert _issues(run) == {(f"{harness.UNIQID}:2", "legacy_journal_lock_applied"): "info"}
    assert notes == [f"{JOURNAL_LOCK_PHASE_KEY}.records.1"]
    observation = run.entity_observations.get(entity_map__entity_type=LOCK_ENTITY_TYPE)
    assert observation.target_model_label == ASSESSMENT_SCHEME_MODEL_LABEL
    assert observation.target_pk == str(scheme.pk)


def test_the_current_period_is_deliberately_left_open(actor):
    future = timezone.localdate() + datetime.timedelta(days=30)
    org, run, report, _rows = _run_phase(actor, "lock-current", period_end=future)

    assert dict(report.state_counts) == {"journal_left_open": 1}
    scheme = _schemes(org).get()
    assert (scheme.approval_status, scheme.is_published) == ("draft", False)
    assert _issues(run) == {(f"{harness.UNIQID}:2", "legacy_journal_lock_deferred"): "info"}


def test_a_period_boundary_today_still_leaves_the_journal_open(actor):
    """Sərhəd şərti: ``end_date < today`` — bugünkü son gün hələ bitməyib."""

    org, _run, report, _rows = _run_phase(actor, "lock-boundary", period_end=timezone.localdate())

    assert dict(report.state_counts) == {"journal_left_open": 1}
    assert _schemes(org).get().is_published is False


def test_a_repeated_invocation_replays_the_sealed_decision(actor):
    rows = harness.tables()
    org = harness.organization(actor, "lock-replay")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk, period_end=datetime.date(2022, 1, 31))
    phase = JournalLockPhase()

    first = phase.run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    second = phase.run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert LegacyEntityMap.objects.filter(entity_type=LOCK_ENTITY_TYPE).count() == 1


def test_the_live_phase_digest_equals_the_ledger_rebuild(actor):
    rows = harness.tables()
    org = harness.organization(actor, "lock-rebuild")
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk, period_end=datetime.date(2022, 1, 31))
    live = JournalLockPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    rebuilt = phase_report_from_ledger(run, phase=JournalLockPhase(), plan=harness.plan(rows))

    assert rebuilt.phase_digest == live.phase_digest
    assert dict(rebuilt.state_counts) == dict(live.state_counts)
