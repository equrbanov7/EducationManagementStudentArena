"""Phase ``journal_reconcile`` (J8) testləri: balans, ``yekun`` güzgüsü, xülasə."""

from django.apps import apps as django_apps

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
)
from apps.legacy_import.services.rehearsal_journal_components_phase import JournalComponentsPhase
from apps.legacy_import.services.rehearsal_journal_finals_phase import JournalFinalsPhase
from apps.legacy_import.services.rehearsal_journal_marks_phase import JournalMarksPhase
from apps.legacy_import.services.rehearsal_journal_reconcile_phase import (
    DERIVED_DIGEST_NAMESPACE,
    FINAL_COVERAGE_KEY,
    ISSUE_SEVERITY,
    JOURNAL_RECONCILE_PHASE_KEY,
    QUARANTINE_SUMMARY_KEY,
    RECONCILE_ENTITY_TYPE,
    JournalReconcilePhase,
    yekun_seal_key,
)
from apps.legacy_import.services.rehearsal_journal_reconcile_source import (
    BALANCE_KEYS,
    balance_delta,
    final_coverage,
)
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db


def test_the_phase_declares_a_batch_less_write_free_shape(db):
    phase = JournalReconcilePhase()

    assert phase.phase_key == JOURNAL_RECONCILE_PHASE_KEY and phase.order == 48
    assert phase.source_tables == () and phase.entity_types == (RECONCILE_ENTITY_TYPE,)
    assert phase.declared_source_rows(harness.plan(harness.tables())) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_ledger_sort_key is str
    assert phase.derived_state_key("skipped") == "reconcile_balanced"
    assert phase.derived_state_key("quarantined") == "reconcile_deviation"


def test_issue_severity_map_covers_exactly_the_reconcile_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_journal_reconcile_row_balance": "info",
        "legacy_journal_reconcile_final_deviation": "info",
        "legacy_journal_reconcile_quarantine_summary": "info",
        "legacy_journal_final_missing": "info",
        "legacy_journal_reconcile_final_unresolved": "warning",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)


def test_the_balance_identity_is_source_minus_unwritable_minus_target():
    bucket = dict.fromkeys(BALANCE_KEYS, 0)
    bucket.update({"source": 10, "empty": 2, "unreadable": 1, "orphan": 1, "overlap": 1})

    assert balance_delta(bucket, 5) == 0  # 10 − 5 yazıla bilən = 5 hədəf
    assert balance_delta(bucket, 4) == 1  # bir sətir dublikat uduzanı olub


def test_the_yekun_seal_key_sorts_lexicographically_like_a_number():
    assert yekun_seal_key(7) == "y-0000000007"
    assert sorted(yekun_seal_key(pk) for pk in (2, 10, 1)) == [
        yekun_seal_key(1),
        yekun_seal_key(2),
        yekun_seal_key(10),
    ]
    assert QUARANTINE_SUMMARY_KEY < yekun_seal_key(1)  # ``a-`` həmişə ``y-``-dən əvvəl


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        JournalReconcilePhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


def test_the_dependency_gate_requires_the_lock_phase():
    rows = harness.tables()
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalReconcilePhase().run(harness.context(rows_by_table=rows, phase_keys=("journal_reconcile",)))

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="journal_reconcile_actor", email="jr-actor@example.test", password="test-only"
    )


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=RECONCILE_ENTITY_TYPE)
    }


def _states(run):
    return dict(
        run.entity_observations.filter(entity_map__entity_type=RECONCILE_ENTITY_TYPE).values_list(
            "entity_map__legacy_pk", "state"
        )
    )


def _pseudo(legacy_pk, month_id, point, **overrides):
    return harness.point_row(legacy_pk, month_id=month_id, day_number=month_id, point=point, **overrides)


def _seeded(actor, slug, rows, *, run_writers=True):
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk)
    if run_writers:
        for phase in (JournalMarksPhase(), JournalComponentsPhase(), JournalFinalsPhase()):
            phase.run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    return org, run


def test_a_fully_written_import_balances_on_every_domain(actor):
    rows = harness.tables(
        points=[
            harness.point_row(1, point="ie"),
            harness.point_row(2, point="8", day_number="31"),
            _pseudo(3, "k1", "9"),
            _pseudo(4, "im", "40"),
        ]
    )
    org, run = _seeded(actor, "reconcile-balanced", rows)
    notes = []
    report = JournalReconcilePhase().run(
        harness.context(rows_by_table=rows, run=run, organization=org, actor=actor, notes=notes)
    )

    # 5 möhür: 3 balans + imtahan nəticəsi örtüyü + karantin xülasəsi.
    assert dict(report.state_counts) == {"reconcile_balanced": 5}
    assert _states(run) == {
        "a-balance-marks": "skipped",
        "a-balance-components": "skipped",
        "a-balance-finals": "skipped",
        FINAL_COVERAGE_KEY: "skipped",
        QUARANTINE_SUMMARY_KEY: "skipped",
    }
    assert _issues(run) == {
        ("a-balance-marks", "legacy_journal_reconcile_row_balance"): "info",
        ("a-balance-components", "legacy_journal_reconcile_row_balance"): "info",
        ("a-balance-finals", "legacy_journal_reconcile_row_balance"): "info",
        # Xanalar YALNIZ STUDENT_A üçündür → STUDENT_B-nin imtahan nəticəsi
        # yoxdur, yəni örtük natamamdır və B-tapşırığının İNFO-su yazılır.
        (FINAL_COVERAGE_KEY, "legacy_journal_final_missing"): "info",
        (QUARANTINE_SUMMARY_KEY, "legacy_journal_reconcile_quarantine_summary"): "info",
    }
    assert notes == [f"{JOURNAL_RECONCILE_PHASE_KEY}.records.5"]


def test_a_duplicate_loser_shows_up_as_a_marks_balance_delta(actor):
    """J-V9(a): mənbə = yazılan + karantin + skip; fərq görünən şəkildə qalır."""

    rows = harness.tables(
        points=[
            harness.point_row(1, point="4", update_counter=0),
            harness.point_row(2, point="9", update_counter=3),
        ]
    )
    org, run = _seeded(actor, "reconcile-delta", rows)
    report = JournalReconcilePhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert dict(report.state_counts) == {"reconcile_balanced": 4, "reconcile_deviation": 1}
    assert _states(run)["a-balance-marks"] == "quarantined"


def test_the_empty_and_unreadable_rows_never_count_as_a_deviation(actor):
    rows = harness.tables(
        points=[
            harness.point_row(1, point=""),
            harness.point_row(2, point="89", day_number="31"),
            _pseudo(3, "pa", "3"),
        ]
    )
    org, run = _seeded(actor, "reconcile-unwritable", rows)
    report = JournalReconcilePhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert dict(report.state_counts) == {"reconcile_balanced": 5}


def test_the_yekun_mirror_matches_a_written_journal(actor):
    """Giriş balı (dərs balları + kollokvium) + imtahan balı — güzgü tam üst-üstə."""

    rows = harness.tables(
        points=[
            harness.point_row(1, point="8"),
            _pseudo(2, "k1", "9"),
            _pseudo(3, "im", "40"),
        ],
        yekun=[harness.yekun_row(1, girish=17.0, imtahanda=40.0, yekun=57.0)],
    )
    org, run = _seeded(actor, "reconcile-yekun-match", rows)
    report = JournalReconcilePhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert _states(run)[yekun_seal_key(1)] == "skipped"
    assert dict(report.state_counts) == {"reconcile_balanced": 6}


def test_a_yekun_deviation_is_reported_as_info_and_quarantined(actor):
    rows = harness.tables(
        points=[harness.point_row(1, point="8")],
        yekun=[harness.yekun_row(1, girish=45.0, imtahanda=50.0, yekun=95.0)],
    )
    org, run = _seeded(actor, "reconcile-yekun-deviation", rows)
    report = JournalReconcilePhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert _states(run)[yekun_seal_key(1)] == "quarantined"
    assert _issues(run)[(yekun_seal_key(1), "legacy_journal_reconcile_final_deviation")] == "info"
    assert report.state_counts["reconcile_deviation"] >= 1


def test_an_unresolvable_yekun_row_is_a_warning(actor):
    rows = harness.tables(yekun=[harness.yekun_row(1, journal_id=999)])
    org, run = _seeded(actor, "reconcile-yekun-orphan", rows)
    report = JournalReconcilePhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert _states(run)[yekun_seal_key(1)] == "quarantined"
    assert _issues(run)[(yekun_seal_key(1), "legacy_journal_reconcile_final_unresolved")] == "warning"
    assert report.state_counts["reconcile_deviation"] == 1


def test_the_quarantine_summary_counts_every_journal_phase(actor):
    rows = harness.tables(
        points=[
            harness.point_row(1, point="89"),  # J4 karantini
            _pseudo(2, "k1", "qb"),  # J5 karantini
            _pseudo(3, "pa", "3"),  # J6 karantini
        ]
    )
    org, run = _seeded(actor, "reconcile-summary", rows)
    JournalReconcilePhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    from apps.legacy_import.services.rehearsal_journal_reconcile_phase import quarantine_summary

    assert quarantine_summary(run.pk) == {
        "journal_marks": 1,
        "journal_components": 1,
        "journal_entry_scores": 0,
        "journal_finals": 1,
        "journal_lock": 0,
    }
    assert (QUARANTINE_SUMMARY_KEY, "legacy_journal_reconcile_quarantine_summary") in _issues(run)


def test_the_phase_writes_no_target_row_of_its_own(actor):
    rows = harness.tables(points=[harness.point_row(1, point="ie")], yekun=[harness.yekun_row(1, yekun=0.0)])
    org, run = _seeded(actor, "reconcile-readonly", rows)
    before = django_apps.get_model("registrar", "LessonMark").objects.filter(organization=org).count()

    JournalReconcilePhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert django_apps.get_model("registrar", "LessonMark").objects.filter(organization=org).count() == before
    assert not run.entity_observations.filter(
        entity_map__entity_type=RECONCILE_ENTITY_TYPE, state=LegacyEntityMap.State.MIGRATED
    ).exists()


def test_a_repeated_invocation_replays_the_sealed_checks(actor):
    rows = harness.tables(
        points=[harness.point_row(1, point="ie")],
        yekun=[harness.yekun_row(1, yekun=0.0)],
    )
    org, run = _seeded(actor, "reconcile-replay", rows)
    phase = JournalReconcilePhase()

    first = phase.run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    second = phase.run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert LegacyEntityMap.objects.filter(entity_type=RECONCILE_ENTITY_TYPE).count() == 6


def test_the_live_phase_digest_equals_the_ledger_rebuild(actor):
    rows = harness.tables(
        points=[harness.point_row(1, point="8"), _pseudo(2, "im", "40")],
        yekun=[harness.yekun_row(1, yekun=48.0), harness.yekun_row(2, journal_id=999)],
    )
    org, run = _seeded(actor, "reconcile-rebuild", rows)
    live = JournalReconcilePhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))
    rebuilt = phase_report_from_ledger(run, phase=JournalReconcilePhase(), plan=harness.plan(rows))

    assert rebuilt.phase_digest == live.phase_digest
    assert dict(rebuilt.state_counts) == dict(live.state_counts)


# ── (d) imtahan nəticəsi örtüyü (B-tapşırığı, 2026-08) ───────────────────────


def test_the_coverage_seal_counts_enrollments_without_any_exam_result(actor):
    """Hər iki tələbənin ``im`` xanası varsa örtük tamdır — İNFO yazılmır."""

    rows = harness.tables(
        points=[
            _pseudo(1, "im", "40"),
            _pseudo(2, "im", "45", student_id=harness.STUDENT_B),
        ]
    )
    org, run = _seeded(actor, "reconcile-coverage-full", rows)
    report = JournalReconcilePhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert final_coverage(_ctx(org)) == {"enrollments": 2, "covered": 2, "missing": 0}
    assert _states(run)[FINAL_COVERAGE_KEY] == "skipped"
    assert (FINAL_COVERAGE_KEY, "legacy_journal_final_missing") not in _issues(run)
    assert "reconcile_deviation" not in report.state_counts


def test_an_enrollment_without_an_exam_result_is_reported_but_never_blocks(actor):
    """Nəticəsiz yazılış İNFO ilə görünür; möhür SKIPPED qalır (karantin DEYİL)."""

    rows = harness.tables(points=[_pseudo(1, "im", "40")])
    org, run = _seeded(actor, "reconcile-coverage-gap", rows)
    JournalReconcilePhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    # STUDENT_B-nin imtahan nəticəsi yoxdur → nə keçir, nə kəsilir.
    assert final_coverage(_ctx(org)) == {"enrollments": 2, "covered": 1, "missing": 1}
    assert _states(run)[FINAL_COVERAGE_KEY] == "skipped"
    assert _issues(run)[(FINAL_COVERAGE_KEY, "legacy_journal_final_missing")] == "info"


class _Ctx:
    """``final_coverage`` yalnız ``organization``-a baxır — minimal ikiüzlü."""

    def __init__(self, organization):
        self.organization = organization


def _ctx(org):
    return _Ctx(org)
