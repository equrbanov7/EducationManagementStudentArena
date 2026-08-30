"""Köhnə qiymət sübutu fazasının itkisizlik və determinizm testləri."""

from decimal import Decimal

from django.apps import apps as django_apps

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyMigrationIssue
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
)
from apps.legacy_import.services.rehearsal_journal_enrollments_phase import (
    JOURNAL_ENROLLMENTS_PHASE_KEY,
)
from apps.legacy_import.services.rehearsal_journal_finals_phase import JOURNAL_FINALS_PHASE_KEY
from apps.legacy_import.services.rehearsal_journal_lock_phase import JOURNAL_LOCK_PHASE_KEY
from apps.legacy_import.services.rehearsal_legacy_grade_facts_phase import (
    DERIVED_DIGEST_NAMESPACE,
    LEGACY_GRADE_FACT_ENTITY_TYPE,
    LEGACY_GRADE_FACTS_PHASE_KEY,
    LegacyGradeFactsPhase,
)
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.tests import journal_points_harness as harness
from core.rls import set_rls_user

pytestmark = pytest.mark.django_db

PHASE_KEYS = (
    JOURNAL_ENROLLMENTS_PHASE_KEY,
    JOURNAL_FINALS_PHASE_KEY,
    JOURNAL_LOCK_PHASE_KEY,
    LEGACY_GRADE_FACTS_PHASE_KEY,
)


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="legacy_grade_fact_actor",
        email="legacy-grade-fact@example.test",
        password="test-only",
    )


def _run(actor, slug, rows, *, seed=True):
    # İstehsal yolunda `execute_rehearsal` faza işləməzdən ƏVVƏL
    # `set_rls_user(actor.pk)` çağırır (rehearsal_orchestrator.py:403, :486).
    # Bu test fazanı orkestratordan YAN KEÇƏRƏK birbaşa çağırdığı üçün həmin
    # GUC-u özü qurmalıdır — əks halda `registrar_guard_legacy_grade_*_insert`
    # trigger-i `app.current_user_id`-ni boş görüb aktoru səlahiyyətsiz sayır
    # («import actor is not authorized»).  SQLite-da belə trigger olmadığından
    # bu boşluq YALNIZ PostgreSQL-də üzə çıxır.
    set_rls_user(actor.pk, local=False)
    org = harness.organization(actor, slug)
    run = harness.running_run(org, actor, table_plan=harness.plan(rows))
    if seed:
        harness.seed_journal_target(org, actor, run.pk)
    context = harness.context(
        rows_by_table=rows,
        run=run,
        organization=org,
        actor=actor,
        phase_keys=PHASE_KEYS,
    )
    report = LegacyGradeFactsPhase().run(context)
    return org, run, report, context


def _facts(org):
    return django_apps.get_model("registrar", "LegacyGradeFact").objects.filter(organization=org)


def _issues(run):
    return {
        (item.legacy_pk, item.rule_code): item.severity
        for item in LegacyMigrationIssue.objects.filter(
            run=run,
            entity_type=LEGACY_GRADE_FACT_ENTITY_TYPE,
        )
    }


def test_phase_shape_and_dependency_gate(db):
    phase = LegacyGradeFactsPhase()

    assert phase.phase_key == LEGACY_GRADE_FACTS_PHASE_KEY
    assert phase.order == 47
    assert phase.source_tables == ()
    assert phase.entity_types == (LEGACY_GRADE_FACT_ENTITY_TYPE,)
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "legacy_grade_facts_materialised"
    assert phase.declared_source_rows(harness.plan(harness.tables())) == 0

    with pytest.raises(LegacyRehearsalConfigError) as invalid:
        phase.run(object())
    assert invalid.value.code == "legacy_rehearsal_context_invalid"

    rows = harness.tables()
    with pytest.raises(LegacyRehearsalEvidenceError) as missing:
        phase.run(harness.context(rows_by_table=rows, phase_keys=(LEGACY_GRADE_FACTS_PHASE_KEY,)))
    assert missing.value.code == "legacy_rehearsal_phase_dependency_missing"


def test_every_summary_and_final_domain_cell_is_preserved_without_clamp(actor):
    rows = harness.tables(
        journals=[
            harness.journal_row(2, harness.UNIQID),
            harness.journal_row(3, harness.OTHER_UNIQID, fake=1),
        ],
        points=[
            harness.point_row(10, month_id="im", point="61"),
            harness.point_row(11, uniqid=harness.OTHER_UNIQID, month_id="im2", point="wr"),
            harness.point_row(12, month_id="k1", point="8"),
        ],
        archive=[harness.point_row(10, month_id="im", point="49")],
        yekun=[
            harness.yekun_row(
                20,
                girish=59.0,
                imtahanda=69.0,
                yekun=117.0,
                kesr=1,
                level=2,
                guzest_girish=4.5,
                guzest_artim=3.25,
            ),
            harness.yekun_row(21, student_id=999, girish=17.25, imtahanda=28.5, yekun=45.75),
        ],
    )

    org, run, report, _context = _run(actor, "grade-facts-complete", rows)

    # 2 yekun + main im + main im2 + archive im.  k1 komponentdir və bu
    # final-domen arxivinə daxil deyil.
    assert _facts(org).count() == 5
    assert dict(report.state_counts) == {"legacy_grade_facts_materialised": 5}

    summary = _facts(org).get(source_table="yekun", source_pk=20)
    assert (
        summary.entry_score_text,
        summary.exam_score_text,
        summary.final_score_text,
    ) == ("59.0", "69.0", "117.0")
    assert (summary.entry_score, summary.exam_score, summary.final_score) == (
        Decimal("59.0000"),
        Decimal("69.0000"),
        Decimal("117.0000"),
    )
    assert (summary.legacy_kesr, summary.legacy_level) == (1, 2)
    assert (summary.legacy_guzest_girish_text, summary.legacy_guzest_artim_text) == (
        "4.5",
        "3.25",
    )
    assert summary.requires_exam_center_review is True
    assert summary.source_enrollment_ref == f"{harness.UNIQID}:{harness.STUDENT_A}"

    main = _facts(org).get(source_table="journals_dates_points", source_pk=10)
    archive = _facts(org).get(source_table="journals_dates_points_archive", source_pk=10)
    assert (main.raw_score_text, main.exam_score, main.is_archive) == (
        "61",
        Decimal("61.0000"),
        False,
    )
    assert (archive.raw_score_text, archive.exam_score, archive.is_archive) == (
        "49",
        Decimal("49.0000"),
        True,
    )

    special = _facts(org).get(source_table="journals_dates_points", source_pk=11)
    assert (special.raw_score_text, special.resit_score, special.mapping_status) == (
        "wr",
        None,
        "discarded_source",
    )
    assert _facts(org).get(source_table="yekun", source_pk=21).mapping_status == "unresolved"
    assert _issues(run) == {
        ("journals_dates_points:10", "legacy_grade_fact_out_of_range"): "warning",
        ("journals_dates_points:11", "legacy_grade_fact_discarded_source"): "warning",
        ("journals_dates_points:11", "legacy_grade_fact_non_numeric"): "warning",
        ("yekun:20", "legacy_grade_fact_out_of_range"): "warning",
        ("yekun:21", "legacy_grade_fact_unresolved"): "warning",
    }


def test_distinct_conflicting_yekun_rows_are_both_kept_and_flagged(actor):
    rows = harness.tables(
        yekun=[
            harness.yekun_row(1, girish=30.0, imtahanda=40.0, yekun=70.0),
            harness.yekun_row(2, girish=31.0, imtahanda=39.0, yekun=70.0),
        ]
    )

    org, run, _report, _context = _run(actor, "grade-facts-conflict", rows)

    facts = list(_facts(org).order_by("source_pk"))
    assert len(facts) == 2
    assert [fact.entry_score_text for fact in facts] == ["30.0", "31.0"]
    assert {fact.mapping_status for fact in facts} == {"conflict"}
    assert _issues(run) == {
        ("yekun:1", "legacy_grade_fact_conflict"): "warning",
        ("yekun:2", "legacy_grade_fact_conflict"): "warning",
    }


def test_every_exam_entry_exit_attempt_keeps_source_pk_type_date_and_raw_scores(actor):
    rows = harness.tables(
        exam_attempts=[
            harness.exam_attempt_row(101, entry=3010, exit=2437, attempt_type=3),
            harness.exam_attempt_row(102, entry=12, exit=39, attempt_type=3),
            harness.exam_attempt_row(103, student_id=999, entry=7, exit=18, attempt_type=1),
        ]
    )

    org, run, report, _context = _run(actor, "grade-facts-attempts", rows)

    facts = _facts(org).filter(source_table="imthngrscxsblr").order_by("source_pk")
    assert list(facts.values_list("source_pk", flat=True)) == [101, 102, 103]
    first = facts[0]
    assert first.evidence_kind == "exam_entry_exit"
    assert (first.entry_score_text, first.exam_score_text) == ("3010", "2437")
    assert (first.entry_score, first.exam_score) == (Decimal("3010.0000"), Decimal("2437.0000"))
    assert first.legacy_attempt_type == 3
    assert first.legacy_recorded_at_text == "2022-04-01 09:00:00"
    assert first.mapping_status == "linked"
    assert facts[1].source_pk == 102  # eyni student/fənn/type sətri merge olunmur
    assert facts[2].mapping_status == "unresolved"
    assert dict(report.state_counts) == {"legacy_grade_facts_materialised": 3}
    assert _issues(run) == {
        ("imthngrscxsblr:101", "legacy_grade_fact_out_of_range"): "warning",
        ("imthngrscxsblr:103", "legacy_grade_fact_unresolved"): "warning",
    }


def test_an_unmapped_source_fact_is_still_materialised(actor):
    rows = harness.tables(
        journals=[harness.journal_row(2, harness.UNIQID)],
        points=[harness.point_row(1, student_id=999, month_id="im", point="37")],
    )

    org, _run_row, report, _context = _run(actor, "grade-facts-unmapped", rows, seed=False)

    fact = _facts(org).get()
    assert fact.enrollment_id is None
    assert fact.mapping_status == "unresolved"
    assert fact.raw_score_text == "37"
    assert dict(report.state_counts) == {"legacy_grade_facts_materialised": 1}


def test_repeat_is_idempotent_and_ledger_rebuild_matches(actor):
    rows = harness.tables(
        points=[harness.point_row(1, month_id="im", point="47")],
        yekun=[harness.yekun_row(2, girish=33.5, imtahanda=47.0, yekun=80.5)],
    )
    org, run, first, context = _run(actor, "grade-facts-replay", rows)

    second = LegacyGradeFactsPhase().run(context)
    rebuilt = phase_report_from_ledger(run, phase=LegacyGradeFactsPhase(), plan=harness.plan(rows))

    assert _facts(org).count() == 2
    assert second.phase_digest == first.phase_digest == rebuilt.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts) == dict(rebuilt.state_counts)


def test_fresh_targets_share_digest_despite_random_enrollment_uuids(actor):
    rows = harness.tables(
        points=[harness.point_row(1, month_id="im", point="47")],
        yekun=[harness.yekun_row(2, girish=33.5, imtahanda=47.0, yekun=80.5)],
    )
    first_org, _first_run, first_report, _first_context = _run(actor, "grade-facts-determinism-a", rows)
    second_org, _second_run, second_report, _second_context = _run(actor, "grade-facts-determinism-b", rows)

    first_fact = _facts(first_org).get(source_table="yekun")
    second_fact = _facts(second_org).get(source_table="yekun")
    assert first_fact.enrollment_id != second_fact.enrollment_id
    assert first_fact.source_enrollment_ref == second_fact.source_enrollment_ref
    assert first_fact.materialization_digest == second_fact.materialization_digest
    assert first_report.phase_digest == second_report.phase_digest


def test_every_materialised_fact_has_a_targeted_ledger_seal(actor):
    rows = harness.tables(
        points=[
            harness.point_row(1, month_id="im", point="40"),
            harness.point_row(2, month_id="im2", point="42"),
        ],
        yekun=[harness.yekun_row(3, girish=40.0, imtahanda=42.0, yekun=82.0)],
    )
    org, run, _report, _context = _run(actor, "grade-facts-ledger", rows)

    seals = LegacyEntityMap.objects.filter(
        created_run=run,
        entity_type=LEGACY_GRADE_FACT_ENTITY_TYPE,
    )
    assert seals.count() == _facts(org).count() == 3
    assert set(seals.values_list("legacy_pk", flat=True)) == {
        "journals_dates_points:1",
        "journals_dates_points:2",
        "yekun:3",
    }
    assert set(seals.values_list("state", flat=True)) == {LegacyEntityMap.State.MIGRATED}
    assert not seals.filter(target_pk="").exists()
