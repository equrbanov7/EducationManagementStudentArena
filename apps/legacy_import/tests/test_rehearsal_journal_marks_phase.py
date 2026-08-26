"""Phase ``journal_marks`` (J4) testləri: J-V1..J-V7 qaydalarının hər biri."""

import datetime
from decimal import Decimal

from django.apps import apps as django_apps

import pytest

from apps.legacy_import.models import LegacyEntityMap, LegacyImportBatch, LegacyMigrationIssue
from apps.legacy_import.services.field_contracts import (
    JOURNAL_POINT_ARCHIVE_FIELDS,
    JOURNAL_POINT_FIELDS,
    is_credential_field,
)
from apps.legacy_import.services.rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
)
from apps.legacy_import.services.rehearsal_journal_marks_phase import (
    DERIVED_DIGEST_NAMESPACE,
    JOURNAL_MARKS_PHASE_KEY,
    JournalMarksPhase,
    classify_mark_cell,
)
from apps.legacy_import.services.rehearsal_journal_marks_targets import ISSUE_SEVERITY, MARKS_ENTITY_TYPE
from apps.legacy_import.services.rehearsal_journal_points_source import (
    CellElection,
    calendar_slot,
    elect_winners,
    normalized_time,
    parse_cell_score,
)
from apps.legacy_import.services.rehearsal_reconciliation import phase_report_from_ledger
from apps.legacy_import.tests import journal_points_harness as harness

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Saf forma / taksonomiya / parse (verilənlər bazasız)
# ---------------------------------------------------------------------------


def test_the_phase_declares_a_batch_less_journal_keyed_shape(db):
    phase = JournalMarksPhase()

    assert phase.phase_key == JOURNAL_MARKS_PHASE_KEY and phase.order == 40
    assert phase.source_tables == () and phase.entity_types == (MARKS_ENTITY_TYPE,)
    assert phase.declared_source_rows(harness.plan(harness.tables())) == 0
    assert phase.derived_digest_namespace == DERIVED_DIGEST_NAMESPACE
    # Açar ``uniqid``-dir: rebuild LEKSİKOQRAFİK sıralamalıdır.
    assert phase.derived_ledger_sort_key is str
    assert phase.derived_state_key(LegacyEntityMap.State.MIGRATED) == "journal_marks_materialised"
    assert phase.derived_state_key("skipped") == "journal_marks_skipped"
    assert phase.derived_state_key("quarantined") == "journal_marks_unresolved"


def test_issue_severity_map_covers_exactly_the_mark_taxonomy():
    assert dict(ISSUE_SEVERITY) == {
        "legacy_journal_mark_score_out_of_range": "warning",
        "legacy_journal_mark_point_unknown": "warning",
        "legacy_journal_mark_enrollment_unresolved": "warning",
        "legacy_journal_mark_lesson_unresolved": "warning",
        "legacy_journal_mark_target_conflict": "warning",
        "legacy_journal_mark_orphan": "info",
        "legacy_journal_mark_duplicate": "info",
        "legacy_journal_mark_empty": "info",
        "legacy_journal_mark_excused": "info",
        "legacy_journal_mark_lab_cell": "info",
        "legacy_journal_archive_overlap": "info",
    }
    assert set(ISSUE_SEVERITY.values()) <= set(LegacyMigrationIssue.Severity.values)


def test_the_point_contracts_are_credential_free_and_default_deny():
    # ``sem_muh`` və ``ga`` QƏSDƏN kənardadır (bax field_contracts qeydi);
    # ``added_date`` isə J-V7 kəsimi üçün lazımdır.
    assert JOURNAL_POINT_FIELDS.allowed_fields == JOURNAL_POINT_ARCHIVE_FIELDS.allowed_fields
    assert "sem_muh" not in JOURNAL_POINT_FIELDS.allowed_fields
    assert "ga" not in JOURNAL_POINT_FIELDS.allowed_fields
    assert "added_date" in JOURNAL_POINT_FIELDS.allowed_fields
    assert not any(is_credential_field(name) for name in JOURNAL_POINT_FIELDS.allowed_fields)
    # Arxiv AYRI kontraktdır: barmaq izi mənbə cədvəlinin adını da bağlayır.
    assert JOURNAL_POINT_FIELDS.fingerprint != JOURNAL_POINT_ARCHIVE_FIELDS.fingerprint


@pytest.mark.parametrize(
    "point, expected",
    [
        # J-V1(F): ``ie`` = İŞTİRAK EDİR (balsız), ``qb`` = qayıb.
        ("ie", ("present", "present", None)),
        ("qb", ("absent", "absent", None)),
        ("0", ("scored", "present", Decimal(0))),
        ("10", ("scored", "present", Decimal(10))),
        ("", ("empty", "", None)),
        # J-V2: 0-10 xaricində rəqəm KARANTİNdir, şkala çevrilmir.
        ("11", ("range", "", None)),
        ("89", ("range", "", None)),
        # J-V13: tanınmayan kod.
        ("l", ("unknown", "", None)),
        ("wr", ("unknown", "", None)),
        (" 5", ("unknown", "", None)),
        ("-1", ("unknown", "", None)),
    ],
)
def test_classify_mark_cell_is_strict(point, expected):
    assert classify_mark_cell(point) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (datetime.timedelta(hours=14), "14:00"),
        (datetime.timedelta(hours=8, minutes=30), "08:30"),
        (datetime.timedelta(0), "00:00"),
        (datetime.timedelta(hours=25), ""),
        (datetime.timedelta(seconds=-60), ""),
        (datetime.time(9, 5), "09:05"),
        ("13:35", "13:35"),
        ("1_:__", ""),
        (None, ""),
        (7, ""),
    ],
)
def test_normalized_time_is_strict(value, expected):
    assert normalized_time(value) == expected


@pytest.mark.parametrize(
    "month_id, day_number, expected",
    [
        ("04", "17", (4, 17)),
        ("12", "01", (12, 1)),
        ("13", "01", None),
        ("00", "01", None),
        ("k1", "k1", None),
        ("04", "00", None),
        ("04", "32", None),
        ("04", "x", None),
    ],
)
def test_calendar_slot_is_strict(month_id, day_number, expected):
    assert calendar_slot(month_id, day_number) == expected


@pytest.mark.parametrize("text, expected", [("7", 7), ("07", 7), ("", None), ("ie", None), ("7.5", None)])
def test_parse_cell_score_accepts_only_unsigned_integers(text, expected):
    assert parse_cell_score(text) == expected


def test_the_election_prefilter_never_produces_a_false_negative():
    """Prefiltr yalnız SÜPERÇOXLUQ verir: hər təkrar açar mütləq namizəddir."""

    election = CellElection(expected_rows=64)
    keys = [(f"j{index % 7}", "12", "30", index % 5, "14:00") for index in range(200)]
    for key in keys:
        election.observe(key)

    repeated = {key for key in keys if keys.count(key) > 1}
    assert repeated
    assert all(election.is_candidate(key) for key in repeated)


def test_elect_winners_follows_the_documented_order():
    """J-V4: ən böyük ``update_counter`` → ən son ``updated_at`` → ən böyük id."""

    key = ("j", "12", "30", 42, "14:00")
    assert elect_winners([(key, (0, "", 1), 1), (key, (3, "", 2), 2), (key, (1, "", 3), 3)]) == {key: 2}
    assert elect_winners([(key, (2, "2024-01-01T00:00:00", 1), 1), (key, (2, "2024-05-01T00:00:00", 2), 2)]) == {key: 2}
    assert elect_winners([(key, (2, "2024-01-01T00:00:00", 1), 1), (key, (2, "2024-01-01T00:00:00", 9), 9)]) == {key: 9}


def test_a_non_context_argument_is_refused():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        JournalMarksPhase().run(object())

    assert exc_info.value.code == "legacy_rehearsal_context_invalid"


@pytest.mark.parametrize(
    "phase_keys",
    [("journal_marks",), ("journal_offerings", "journal_marks"), ("journal_lessons", "journal_marks")],
)
def test_the_dependency_gate_is_evidence_not_config(phase_keys):
    rows = harness.tables()
    with pytest.raises(LegacyRehearsalEvidenceError) as exc_info:
        JournalMarksPhase().run(harness.context(rows_by_table=rows, phase_keys=phase_keys))

    assert exc_info.value.code == "legacy_rehearsal_phase_dependency_missing"


# ---------------------------------------------------------------------------
# Ledger-li mühit
# ---------------------------------------------------------------------------


@pytest.fixture()
def actor(db, django_user_model):
    return django_user_model.objects.create_superuser(
        username="journal_marks_actor", email="journal-marks-actor@example.test", password="test-only"
    )


def _marks(org):
    return django_apps.get_model("registrar", "LessonMark").objects.filter(organization=org)


def _states(run):
    return dict(
        run.entity_observations.filter(entity_map__entity_type=MARKS_ENTITY_TYPE).values_list(
            "entity_map__legacy_pk", "state"
        )
    )


def _issues(run):
    return {
        (issue.legacy_pk, issue.rule_code): issue.severity
        for issue in LegacyMigrationIssue.objects.filter(run=run, entity_type=MARKS_ENTITY_TYPE)
    }


def _run_phase(actor, slug, rows, *, seed=True, notes=None, run=None, org=None, **seed_kwargs):
    org = org or harness.organization(actor, slug)
    run = run or harness.running_run(org, actor, table_plan=harness.plan(rows))
    if seed:
        harness.seed_journal_target(org, actor, run.pk, **seed_kwargs)
    report = JournalMarksPhase().run(
        harness.context(rows_by_table=rows, run=run, organization=org, actor=actor, notes=notes)
    )
    return org, run, report


def test_the_happy_path_writes_every_cell_shape(actor):
    rows = harness.tables(
        points=[
            harness.point_row(1, point="ie"),
            harness.point_row(2, point="qb", student_id=harness.STUDENT_B),
            harness.point_row(3, point="8", day_number="31"),
            harness.point_row(4, point="", day_number="31", student_id=harness.STUDENT_B),
        ]
    )
    notes = []
    org, run, report = _run_phase(actor, "marks-happy", rows, notes=notes)

    assert dict(report.state_counts) == {"journal_marks_materialised": 1}
    assert _states(run) == {harness.UNIQID: "migrated"}
    # J-V1(F): ie → PRESENT(balsız), qb → ABSENT, rəqəm → PRESENT + bal, '' → mark YOX.
    by_status = sorted((mark.status, str(mark.score)) for mark in _marks(org))
    assert by_status == [("absent", "None"), ("present", "8.00"), ("present", "None")]
    assert _issues(run) == {(harness.UNIQID, "legacy_journal_mark_empty"): "info"}
    assert notes == [f"{JOURNAL_MARKS_PHASE_KEY}.records.1", f"{JOURNAL_MARKS_PHASE_KEY}.cells.4"]
    assert LegacyImportBatch.objects.filter(run=run).count() == 0
    # Jurnal möhürü açılışı göstərir (spec B.6: sətir-başına map YOXDUR).
    observation = run.entity_observations.get(entity_map__entity_type=MARKS_ENTITY_TYPE)
    assert observation.target_model_label == "registrar.courseoffering"


def test_absence_hours_count_absent_but_never_excused(actor):
    rows = harness.tables(
        points=[
            harness.point_row(1, point="qb"),
            harness.point_row(2, point="qb", day_number="31", excusable=1),
        ]
    )
    org, _run, _report = _run_phase(actor, "marks-absence", rows)

    enrollment = django_apps.get_model("registrar", "Enrollment").objects.get(
        organization=org, student__username=f"myedu.student.{harness.STUDENT_A}"
    )
    # İki dərs × 2 saat, amma yalnız biri ``absent`` — üzürlü qaib sayılmır.
    assert enrollment.absence_hours == 2
    assert sorted(mark.status for mark in _marks(org)) == ["absent", "excused"]


def test_an_out_of_range_or_unknown_point_quarantines_the_journal(actor):
    rows = harness.tables(
        points=[
            harness.point_row(1, point="89"),
            harness.point_row(2, point="l", day_number="31"),
        ]
    )
    org, run, report = _run_phase(actor, "marks-quarantine", rows)

    assert dict(report.state_counts) == {"journal_marks_unresolved": 1}
    assert _states(run) == {harness.UNIQID: "quarantined"}
    assert _issues(run) == {
        (harness.UNIQID, "legacy_journal_mark_score_out_of_range"): "warning",
        (harness.UNIQID, "legacy_journal_mark_point_unknown"): "warning",
    }
    assert _marks(org).count() == 0


def test_the_duplicate_winner_is_the_highest_update_counter(actor):
    """J-V4: qalib yazılır, uduzan qeydli SKIPPED (mənbədə heç nə silinmir)."""

    rows = harness.tables(
        points=[
            harness.point_row(1, point="4", update_counter=0),
            harness.point_row(2, point="9", update_counter=3),
            harness.point_row(3, point="5", update_counter=1),
        ]
    )
    org, run, _report = _run_phase(actor, "marks-duplicate", rows)

    assert _marks(org).get().score == Decimal("9.00")
    assert _issues(run) == {(harness.UNIQID, "legacy_journal_mark_duplicate"): "info"}


def test_the_duplicate_tie_breaks_on_updated_at_then_id(actor):
    rows = harness.tables(
        points=[
            harness.point_row(1, point="4", update_counter=2, updated_at=datetime.datetime(2024, 1, 1)),
            harness.point_row(2, point="7", update_counter=2, updated_at=datetime.datetime(2024, 5, 1)),
            harness.point_row(3, point="6", update_counter=2, updated_at=datetime.datetime(2024, 5, 1)),
        ]
    )
    org, _run, _report = _run_phase(actor, "marks-duplicate-tie", rows)

    # Ən son ``updated_at`` iki sətirdə eynidir → ən böyük id (3) udur.
    assert _marks(org).get().score == Decimal("6.00")


def test_an_allowed_qb_window_turns_an_absence_into_an_excused_one(actor):
    """J-V3: pəncərəyə düşən qayıb EXCUSED, düşməyən ABSENT qalır."""

    rows = harness.tables(
        points=[
            harness.point_row(1, point="qb"),  # 2021-12-30 → pəncərədə
            harness.point_row(2, point="qb", day_number="31", student_id=harness.STUDENT_B),
        ],
        allowed=[harness.allowed_qb_row(1, start="2021-12-30", end="2021-12-30")],
    )
    org, run, _report = _run_phase(actor, "marks-excused", rows)

    assert sorted(mark.status for mark in _marks(org)) == ["absent", "excused"]
    assert (harness.UNIQID, "legacy_journal_mark_excused") in _issues(run)


def test_the_excuse_texts_are_attested_by_the_seal_not_stored(actor):
    """J-V3: ``why``/``description`` ledger-ə OXUNAQLI düşmür, möhürə qatlanır."""

    def _digest(slug, why, description):
        rows = harness.tables(points=[harness.point_row(1, point="qb", excusable=1, why=why, description=description)])
        _org, run, report = _run_phase(actor, slug, rows)
        stored = " ".join(
            run.entity_observations.filter(entity_map__entity_type=MARKS_ENTITY_TYPE).values_list(
                "source_row_hash", flat=True
            )
        )
        assert why not in stored and description not in stored
        return report.phase_digest

    plain = _digest("marks-evidence-a", "xəstəlik", "arayış 12")
    other = _digest("marks-evidence-b", "ezamiyyət", "əmr 7")
    same = _digest("marks-evidence-c", "xəstəlik", "arayış 12")

    assert plain != other  # fərqli sənəd qeydi → fərqli qərar kimliyi
    assert plain == same  # eyni qeyd → cross-run sabit


def test_rows_of_an_unmigrated_journal_are_skipped_as_orphans(actor):
    rows = harness.tables(
        journals=[harness.journal_row(2, harness.UNIQID), harness.journal_row(3, "fakeAAAAAA", fake=1)],
        points=[harness.point_row(1, uniqid="fakeAAAAAA", point="ie")],
    )
    org, run, report = _run_phase(actor, "marks-orphan", rows)

    assert dict(report.state_counts) == {"journal_marks_skipped": 1}
    assert _states(run) == {"fakeAAAAAA": "skipped"}
    assert _issues(run) == {("fakeAAAAAA", "legacy_journal_mark_orphan"): "info"}
    assert _marks(org).count() == 0


def test_unresolved_enrollment_and_lesson_are_reported_separately(actor):
    rows = harness.tables(
        points=[
            harness.point_row(1, point="ie", student_id=999),  # J2-də yoxdur
            harness.point_row(2, point="ie", day_number="15"),  # J3-də belə slot yoxdur
        ]
    )
    org, run, report = _run_phase(actor, "marks-unresolved", rows)

    assert dict(report.state_counts) == {"journal_marks_skipped": 1}
    assert _issues(run) == {
        (harness.UNIQID, "legacy_journal_mark_enrollment_unresolved"): "warning",
        (harness.UNIQID, "legacy_journal_mark_lesson_unresolved"): "warning",
    }
    assert _marks(org).count() == 0


def test_a_broken_calendar_day_is_accounted_not_silently_dropped(actor):
    """Say balansı (J8) yalnız HƏR sətrin hesaba alınması ilə mümkündür."""

    rows = harness.tables(points=[harness.point_row(1, point="ie", day_number="00")])
    org, run, report = _run_phase(actor, "marks-broken-day", rows)

    assert dict(report.state_counts) == {"journal_marks_skipped": 1}
    assert _issues(run) == {(harness.UNIQID, "legacy_journal_mark_lesson_unresolved"): "warning"}
    assert _marks(org).count() == 0


def test_a_lab_cell_is_recorded_but_never_changes_the_lesson_kind(actor):
    """J-V5: J3 dərsi ``lecture`` yaradıb — ``lab=1`` yalnız qeyddir."""

    rows = harness.tables(points=[harness.point_row(1, point="7", lab=1)])
    org, run, _report = _run_phase(actor, "marks-lab", rows)

    assert (harness.UNIQID, "legacy_journal_mark_lab_cell") in _issues(run)
    assert _marks(org).get().score == Decimal("7.00")
    assert {
        lesson.kind for lesson in django_apps.get_model("registrar", "Lesson").objects.filter(organization=org)
    } == {"lecture"}


def test_the_archive_is_a_source_only_before_the_cutoff(actor):
    """J-V7: kəsimdən sonrakı arxiv sətri idxal edilmir (əsas cədvəl udur)."""

    rows = harness.tables(
        archive=[
            harness.point_row(1, point="7", added_date=harness.BEFORE_CUTOFF),
            harness.point_row(2, point="3", day_number="31", added_date=harness.AFTER_CUTOFF),
        ]
    )
    org, run, _report = _run_phase(actor, "marks-archive", rows)

    assert [mark.score for mark in _marks(org)] == [Decimal("7.00")]
    assert (harness.UNIQID, "legacy_journal_archive_overlap") in _issues(run)


def test_the_main_table_wins_over_a_pre_cutoff_archive_row(actor):
    rows = harness.tables(
        points=[harness.point_row(1, point="9")],
        archive=[harness.point_row(1, point="2", added_date=harness.BEFORE_CUTOFF)],
    )
    org, run, _report = _run_phase(actor, "marks-archive-precedence", rows)

    assert _marks(org).get().score == Decimal("9.00")
    assert (harness.UNIQID, "legacy_journal_archive_overlap") in _issues(run)


def test_a_repeated_invocation_replays_the_sealed_journal(actor):
    rows = harness.tables(
        points=[
            harness.point_row(1, point="ie"),
            harness.point_row(2, point="89", day_number="31"),
        ]
    )
    org, run, first = _run_phase(actor, "marks-replay", rows)
    second = JournalMarksPhase().run(harness.context(rows_by_table=rows, run=run, organization=org, actor=actor))

    assert second.phase_digest == first.phase_digest
    assert dict(second.state_counts) == dict(first.state_counts)
    assert LegacyEntityMap.objects.filter(entity_type=MARKS_ENTITY_TYPE).count() == 1
    assert _marks(org).count() == 1


def test_the_live_phase_digest_equals_the_lexicographic_ledger_rebuild(actor):
    rows = harness.tables(
        journals=[harness.journal_row(2, harness.UNIQID), harness.journal_row(3, "fakeAAAAAA", fake=1)],
        points=[
            harness.point_row(1, point="ie"),
            harness.point_row(2, point="89", day_number="31"),
            harness.point_row(3, uniqid="fakeAAAAAA", point="ie"),
        ],
    )
    org, run, live = _run_phase(actor, "marks-rebuild", rows)
    phase = JournalMarksPhase()
    rebuilt = phase_report_from_ledger(run, phase=phase, plan=harness.plan(rows))

    assert rebuilt.phase_digest == live.phase_digest
    assert dict(rebuilt.state_counts) == dict(live.state_counts)
    assert rebuilt.source_tables == live.source_tables == ()
    assert rebuilt.batches == live.batches == ()


def test_the_phase_digest_is_identical_across_two_independent_runs(actor):
    """Cross-run determinizm: zəncirə heç bir UUID və target kimliyi girmir."""

    rows = harness.tables(
        points=[
            harness.point_row(1, point="ie"),
            harness.point_row(2, point="qb", day_number="31"),
            harness.point_row(3, point="l", day_number="31", student_id=harness.STUDENT_B),
        ]
    )
    digests = []
    for slug in ("marks-run-a", "marks-run-b"):
        _org, _run, report = _run_phase(actor, slug, rows)
        digests.append(report.phase_digest)

    assert digests[0] == digests[1]
