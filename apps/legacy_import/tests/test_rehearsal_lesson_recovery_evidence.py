"""J12 hədəfsiz təqvim xanalarının itkisiz ``LegacyGradeFact`` sübutu."""

import datetime
from collections import Counter
from types import SimpleNamespace

from django.apps import apps as django_apps

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue
from apps.legacy_import.services import rehearsal_journal_seal as seal_module
from apps.legacy_import.services import rehearsal_lesson_recovery_conflicts as conflict_module
from apps.legacy_import.services import rehearsal_lesson_recovery_evidence as evidence_module
from apps.legacy_import.services.rehearsal_journal_cells import JournalCellLedger
from apps.legacy_import.services.rehearsal_journal_marks_phase import JournalMarksPhase
from apps.legacy_import.services.rehearsal_journal_points_source import POINT_ARCHIVE_TABLE, POINT_SOURCE_TABLE
from apps.legacy_import.services.rehearsal_journal_seal import JournalSealEntry, JournalSealer
from apps.legacy_import.services.rehearsal_lesson_recovery_evidence import (
    FACT_UNRESOLVED_ISSUE_CODE,
    LESSON_UNRESOLVED_RULE_CODE,
    MARK_UNRESOLVED_ENTITY_TYPE,
    MARK_UNRESOLVED_SEALER,
    UnresolvedFact,
    UnresolvedFactWriter,
)
from apps.legacy_import.services.rehearsal_lesson_recovery_phase import JournalLessonRecoveryPhase
from apps.legacy_import.services.rehearsal_lesson_recovery_scan import (
    RecoveryMarkCell,
    distill_recovery_cell,
)
from apps.legacy_import.services.rehearsal_lesson_recovery_targets import (
    MARK_CONFLICT_ENTITY_TYPE,
    MARK_CONFLICT_SEALER,
    MARK_RECOVERY_ENTITY_TYPE,
    MARK_RECOVERY_SEALER,
    ConflictFact,
    ConflictFactWriter,
    conflict_seal_key,
)
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db


@pytest.fixture
def actor(django_user_model):
    return django_user_model.objects.create_user(username="recovery-evidence-actor", password="x")


def _seed(actor, slug, rows):
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    harness.seed_journal_target(org, actor, run.pk, lesson_slots=())
    context = harness.context(rows_by_table=rows, run=run, organization=org, actor=actor)
    return org, run, context


def test_invalid_main_and_archive_rows_keep_exact_raw_evidence_and_unique_source_keys(actor):
    main = harness.point_row(7, point="06", month_id="11", day_number="31")
    archive = harness.point_row(
        7,
        point="qb",
        month_id="11",
        day_number="31",
        added_date=datetime.datetime(2022, 3, 1, 8, 0),
    )
    rows = harness.tables(dates=[], points=[main], archive=[archive])
    org, run, context = _seed(actor, "recover-raw-evidence", rows)
    harness.authorize_import_actor(org, actor)
    try:
        JournalMarksPhase().run(context)
        first = JournalLessonRecoveryPhase().run(context)
        second = JournalLessonRecoveryPhase().run(context)
    finally:
        harness.clear_import_actor()

    facts = {
        (fact.source_table, fact.source_pk): fact
        for fact in django_apps.get_model("registrar", "LegacyGradeFact").objects.filter(organization=org)
    }
    assert set(facts) == {(POINT_SOURCE_TABLE, 7), (POINT_ARCHIVE_TABLE, 7)}
    assert facts[(POINT_SOURCE_TABLE, 7)].raw_score_text == "06"
    assert facts[(POINT_ARCHIVE_TABLE, 7)].raw_score_text == "qb"
    assert facts[(POINT_SOURCE_TABLE, 7)].source_row_hash == distill_recovery_cell(7, main, False).row_hash
    assert facts[(POINT_ARCHIVE_TABLE, 7)].source_row_hash == distill_recovery_cell(7, archive, True).row_hash
    assert all(
        fact.mapping_status == "unresolved"
        and fact.mapping_issue_code == FACT_UNRESOLVED_ISSUE_CODE
        and fact.requires_exam_center_review is True
        and fact.enrollment_id is None
        for fact in facts.values()
    )
    assert facts[(POINT_SOURCE_TABLE, 7)].is_archive is False
    assert facts[(POINT_ARCHIVE_TABLE, 7)].is_archive is True
    assert first.phase_digest == second.phase_digest
    assert LegacyEntityMap.objects.filter(created_run=run, entity_type=MARK_UNRESOLVED_ENTITY_TYPE).count() == 2


def test_valid_but_still_unresolved_lesson_also_materializes_the_raw_fact(actor):
    rows = harness.tables()
    org, run, context = _seed(actor, "recover-still-unresolved", rows)
    ledger = JournalCellLedger(recorded={})
    unresolved = UnresolvedFactWriter(context, run=run)
    cell = RecoveryMarkCell(
        legacy_pk=91,
        uniqid=harness.UNIQID,
        student_id=harness.STUDENT_A,
        month=12,
        day=30,
        time_text="14:00",
        point="7",
        excusable=0,
        lab=0,
        from_archive=False,
        why="",
        description="",
        row_hash="b" * 64,
    )
    resolution = SimpleNamespace(
        slices=SimpleNamespace(has_offering=lambda _uniqid: True),
        enrollments={f"{harness.UNIQID}:{harness.STUDENT_A}": "enrollment-placeholder"},
        offerings={"enrollment-placeholder": "offering-placeholder"},
        lessons={},
    )
    harness.authorize_import_actor(org, actor)
    try:
        JournalLessonRecoveryPhase()._decide(
            cell=cell,
            resolution=resolution,
            ledger=ledger,
            writer=SimpleNamespace(enqueue=lambda **_kwargs: None),
            unresolved=unresolved,
            years={harness.UNIQID: 2021},
        )
        unresolved.flush()
    finally:
        harness.clear_import_actor()

    fact = django_apps.get_model("registrar", "LegacyGradeFact").objects.get(organization=org)
    assert fact.raw_score_text == "7" and fact.source_row_hash == "b" * 64
    assert ledger.tallies[harness.UNIQID]["lesson"] == 1
    assert set(
        LegacyMigrationIssue.objects.filter(run=run, entity_type=MARK_UNRESOLVED_ENTITY_TYPE).values_list(
            "rule_code", flat=True
        )
    ) == {"legacy_mark_unresolved_evidence", LESSON_UNRESOLVED_RULE_CODE}


def test_fact_and_seal_roll_back_together_and_the_same_writer_can_resume(actor, monkeypatch):
    rows = harness.tables()
    org, run, context = _seed(actor, "recover-evidence-atomic", rows)
    fact = UnresolvedFact(
        source_table=POINT_SOURCE_TABLE,
        legacy_pk=101,
        source_row_hash="a" * 64,
        uniqid=harness.UNIQID,
        student_ref=str(harness.STUDENT_A),
        month_id="11",
        day=31,
        time_text="14:00",
        raw_score_text="09",
        issue_code="legacy_lesson_synth_date_invalid",
    )
    writer = UnresolvedFactWriter(context, run=run)
    writer.add(fact)
    original = JournalSealer.seal_many

    def interrupt_after_seal(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected after fact and seal")

    harness.authorize_import_actor(org, actor)
    try:
        monkeypatch.setattr(evidence_module.JournalSealer, "seal_many", interrupt_after_seal)
        with pytest.raises(RuntimeError, match="injected after fact"):
            writer.flush()
        assert not django_apps.get_model("registrar", "LegacyGradeFact").objects.filter(organization=org).exists()
        assert not LegacyEntityMap.objects.filter(created_run=run, entity_type=MARK_UNRESOLVED_ENTITY_TYPE).exists()

        monkeypatch.setattr(evidence_module.JournalSealer, "seal_many", original)
        writer.flush()
    finally:
        harness.clear_import_actor()

    stored = django_apps.get_model("registrar", "LegacyGradeFact").objects.get(organization=org)
    assert stored.raw_score_text == "09" and stored.source_pk == 101
    assert writer.written == 1 and writer.already == 0
    assert LegacyEntityMap.objects.get(created_run=run, entity_type=MARK_UNRESOLVED_ENTITY_TYPE).target_pk == str(
        stored.pk
    )
    assert MARK_UNRESOLVED_SEALER.recorded_decisions(context)


def test_conflict_fact_and_seal_roll_back_together_then_recorded_resume_is_a_noop(actor, monkeypatch):
    rows = harness.tables()
    org, run, context = _seed(actor, "recover-conflict-atomic", rows)
    enrollment = django_apps.get_model("registrar", "Enrollment").objects.filter(organization=org).first()
    fact = ConflictFact(
        seal_key=conflict_seal_key(from_archive=False, legacy_pk=102),
        source_table=POINT_SOURCE_TABLE,
        legacy_pk=102,
        source_row_hash="b" * 64,
        uniqid=harness.UNIQID,
        student_ref=str(harness.STUDENT_A),
        enrollment_pk=str(enrollment.pk),
        month_id="11",
        losing_text="3",
        winning_text="8",
        target_ref="",
        issue_code="legacy_journal_mark_recovered_target_conflict",
    )
    writer = ConflictFactWriter(context, run=run)
    writer.add(fact)
    original = JournalSealer.seal_many

    def interrupt_after_seal(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected after conflict fact and seal")

    harness.authorize_import_actor(org, actor)
    try:
        monkeypatch.setattr(conflict_module.JournalSealer, "seal_many", interrupt_after_seal)
        with pytest.raises(RuntimeError, match="injected after conflict"):
            writer.flush()
        assert not django_apps.get_model("registrar", "LegacyGradeFact").objects.filter(organization=org).exists()
        assert not LegacyEntityMap.objects.filter(created_run=run, entity_type=MARK_CONFLICT_ENTITY_TYPE).exists()

        monkeypatch.setattr(conflict_module.JournalSealer, "seal_many", original)
        writer.flush()
        recorded = MARK_CONFLICT_SEALER.recorded_decisions(context)
        resumed = ConflictFactWriter(context, run=run, recorded=recorded)
        resumed.add(fact)
        resumed.flush()
    finally:
        harness.clear_import_actor()

    assert django_apps.get_model("registrar", "LegacyGradeFact").objects.filter(organization=org).count() == 1
    assert LegacyEntityMap.objects.filter(created_run=run, entity_type=MARK_CONFLICT_ENTITY_TYPE).count() == 1
    assert resumed.written == 0 and resumed.already == 0
    assert resumed.sealed == [(fact.seal_key, recorded[fact.seal_key])]


def test_journal_map_and_issues_are_one_crash_boundary(actor, monkeypatch):
    rows = harness.tables()
    org, run, context = _seed(actor, "recover-journal-seal-atomic", rows)
    entry = JournalSealEntry(
        seal_key=f"mr:{harness.UNIQID}",
        digest="c" * 64,
        state=LegacyEntityMap.State.QUARANTINED,
        rule_codes=("legacy_lesson_synth_date_invalid",),
    )
    original = seal_module.record_issues

    def interrupt_after_issues(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected after journal issues")

    harness.authorize_import_actor(org, actor)
    try:
        monkeypatch.setattr(seal_module, "record_issues", interrupt_after_issues)
        with pytest.raises(RuntimeError, match="injected after journal issues"):
            MARK_RECOVERY_SEALER.seal_many(context, [entry], issue_counts=Counter())

        assert not LegacyEntityMap.objects.filter(created_run=run, entity_type=MARK_RECOVERY_ENTITY_TYPE).exists()
        assert not LegacyMigrationIssue.objects.filter(run=run, entity_type=MARK_RECOVERY_ENTITY_TYPE).exists()
        assert MARK_RECOVERY_SEALER.recorded_decisions(context) == {}

        monkeypatch.setattr(seal_module, "record_issues", original)
        MARK_RECOVERY_SEALER.seal_many(context, [entry], issue_counts=Counter())
    finally:
        harness.clear_import_actor()

    assert MARK_RECOVERY_SEALER.recorded_decisions(context) == {
        entry.seal_key: (entry.state, entry.digest, entry.label)
    }
    assert (
        LegacyMigrationIssue.objects.filter(
            run=run,
            entity_type=MARK_RECOVERY_ENTITY_TYPE,
            legacy_pk=entry.seal_key,
            rule_code="legacy_lesson_synth_date_invalid",
        ).count()
        == 1
    )
