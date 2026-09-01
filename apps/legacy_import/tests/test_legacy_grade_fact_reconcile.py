"""Immutable legacy grade fact uzlaşdırmasının bazasız unit testləri."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from scripts.legacy_reconcile.grade_facts import (
    SOURCE_GRADE_FACT_ROWS_SQL,
    TARGET_GRADE_FACT_ROWS_SQL,
    _materialization_digest,
    reconcile_grade_facts,
    render_grade_fact_reconciliation,
)
from scripts.legacy_reconcile.grade_replay_facts import replay_grade_fact_rows
from scripts.legacy_reconcile.transport import assert_read_only


class FakeReader:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def query(self, label, sql, params=None):
        self.calls.append((label, sql, params))
        return list(self.rows)


def _source_summary(*, source_pk="1", final="71"):
    return [
        "yekun",
        source_pk,
        "summary",
        "yekun",
        "0",
        "101",
        "202",
        "303",
        "404",
        "journal-x:101",
        "39",
        "32",
        "",
        final,
        "",
        "39",
        "32",
        "NULL",
        final,
        "0",
        "1",
        "0",
        "0",
        "NULL",
        "",
    ]


def _source_point(*, source_pk="5", code="im", raw="045", table="journals_dates_points"):
    kind = "exam" if code == "im" else "resit" if code == "im2" else "other"
    numeric = raw if raw.isdigit() else "NULL"
    return [
        table,
        source_pk,
        kind,
        code,
        "1" if table.endswith("archive") else "0",
        "101",
        "journal-x",
        "",
        "",
        "journal-x:101",
        "",
        raw if code == "im" else "",
        raw if code == "im2" else "",
        "",
        raw,
        "NULL",
        numeric if code == "im" else "NULL",
        numeric if code == "im2" else "NULL",
        "NULL",
        "NULL",
        "NULL",
        "",
        "",
        "NULL",
        "",
    ]


def _source_attempt(*, source_pk="7", entry="3010", exit="2437", attempt_type="3"):
    return [
        "imthngrscxsblr",
        source_pk,
        "exam_entry_exit",
        "exam_entry_exit",
        "0",
        "101",
        "",
        "303",
        "",
        "",
        entry,
        exit,
        "",
        "",
        "",
        entry,
        exit,
        "NULL",
        "NULL",
        "NULL",
        "NULL",
        "",
        "",
        attempt_type,
        "2022-04-01 09:00:00",
    ]


def _target(source_row, *, status="linked", issue="", enrollment="enrollment-uuid"):
    row = list(source_row)
    if row[0] == "imthngrscxsblr" and enrollment:
        row[6] = "journal-x"
        row[9] = "journal-x:101"
    if row[2] == "summary":
        for index in (10, 11, 13, 21, 22):
            if row[index] not in (None, "", "NULL"):
                row[index] = str(float(row[index]))
    # PostgreSQL Decimal scale və MariaDB CAST mətn forması fərqli ola bilər;
    # müqavilə rəqəmin özünü dəqiq müqayisə edir, formatdakı son sıfırı yox.
    for index in range(15, 19):
        if row[index] not in (None, "", "NULL"):
            row[index] = Decimal(str(row[index])).quantize(Decimal("0.0001"))
    row.extend(
        [
            True,  # 25 requires_exam_center_review
            status,
            issue,
            enrollment,
            True,  # enrollment organization matches
            "a" * 64,  # source_row_hash
            "",  # materialization_digest — aşağıda hesablanır
            "b" * 64,  # source snapshot
            "rehearsal-identity-v1.test",
            "fact-uuid",
            "map-uuid",
            "migrated",
            "registrar.legacygradefact",
            "fact-uuid",
            "",  # map digest — aşağıda doldurulur
            "observation-uuid",
            "migrated",
            "registrar.legacygradefact",
            "fact-uuid",
            "",  # observation digest — aşağıda doldurulur
            "enrollment-map-uuid" if enrollment else "",
            "migrated" if enrollment else "",
            enrollment,
        ]
    )
    digest = _materialization_digest(row)
    row[31] = digest
    row[39] = digest
    row[44] = digest
    return row


def test_reconciliation_passes_for_exact_summary_and_point_payloads():
    source_rows = [
        _source_summary(),
        _source_point(raw="045"),
        _source_point(source_pk="6", code="pa", raw="rr"),
        _source_attempt(),
    ]
    target_rows = [_target(row) for row in source_rows]

    result = reconcile_grade_facts(FakeReader(source_rows), FakeReader(target_rows), run_id="run-uuid")

    assert result.passed
    assert result.source_rows == result.target_rows == 4
    assert result.source_by_table == {"imthngrscxsblr": 1, "journals_dates_points": 2, "yekun": 1}
    assert result.source_by_code == {"exam_entry_exit": 1, "im": 1, "pa": 1, "yekun": 1}
    assert result.mapping_statuses == {"linked": 4}


def test_j12_conflict_and_unresolved_rows_are_part_of_the_exact_source_gate():
    conflict = SimpleNamespace(
        domain="marks",
        source_table="journals_dates_points",
        source_pk=81,
        is_archive=False,
        student_ref="101",
        journal_uniqid="journal-x",
        target_ref="lesson-uuid",
        month_id="03",
        raw_value="7",
    )
    unresolved = SimpleNamespace(
        source_table="journals_dates_points_archive",
        source_pk=91,
        is_archive=True,
        student_ref="102",
        journal_uniqid="journal-y",
        month=2,
        day=30,
        time_text="11:30",
        raw_value="9",
    )
    extra = replay_grade_fact_rows(
        SimpleNamespace(
            conflict_evidence=[conflict],
            unresolved_calendar_evidence=[unresolved],
        )
    )
    conflict_target = _target(
        extra[0],
        status="conflict",
        issue="legacy_grade_fact_conflict",
        enrollment="enrollment-uuid",
    )
    unresolved_target = _target(
        extra[1],
        status="unresolved",
        issue="legacy_grade_fact_unresolved",
        enrollment="",
    )

    result = reconcile_grade_facts(
        FakeReader([]),
        FakeReader([conflict_target, unresolved_target]),
        run_id="run-uuid",
        extra_source_rows=extra,
    )

    assert result.passed
    assert result.source_rows == result.target_rows == 2
    assert extra[0][7] == "lesson-uuid"
    assert extra[1][7] == "calendar:02:30:11:30"
    assert result.mapping_statuses == {"conflict": 1, "unresolved": 1}


def test_reconciliation_detects_missing_extra_duplicate_and_payload_drift():
    source_rows = [_source_summary(), _source_summary(), _source_point()]
    target_rows = [
        _target(_source_summary(final="72")),
        _target(_source_point(source_pk="999")),
    ]

    result = reconcile_grade_facts(FakeReader(source_rows), FakeReader(target_rows), run_id="run-uuid")

    assert not result.passed
    assert result.source_duplicates == 1
    assert result.missing_keys == 1
    assert result.extra_keys == 1
    assert result.payload_mismatches == 1


def test_reconciliation_detects_review_tenant_ledger_and_digest_guard_failures():
    source = _source_summary()
    target = _target(source)
    target[25] = False
    target[29] = False
    target[39] = "c" * 64
    target[40] = ""
    target[10] = "40"

    result = reconcile_grade_facts(FakeReader([source]), FakeReader([target]), run_id="run-uuid")

    assert not result.passed
    assert result.payload_mismatches == 1
    assert result.guard_failures["review_required_false"] == 1
    assert result.guard_failures["enrollment_tenant_mismatch"] == 1
    assert result.guard_failures["materialization_digest_invalid"] == 1
    assert result.guard_failures["ledger_map_digest_invalid"] == 1
    assert result.guard_failures["ledger_observation_missing"] == 1


def test_non_linked_mapping_requires_named_issue_and_no_enrollment():
    source = _source_point(code="im2", raw="49")
    target = _target(
        source,
        status="unresolved",
        issue="legacy_grade_fact_unresolved",
        enrollment="",
    )
    result = reconcile_grade_facts(FakeReader([source]), FakeReader([target]), run_id="run-uuid")
    assert result.passed

    target[27] = ""
    result = reconcile_grade_facts(FakeReader([source]), FakeReader([target]), run_id="run-uuid")
    assert result.guard_failures["mapping_issue_mismatch"] == 1

    target = _target(
        source,
        status="unresolved",
        issue="legacy_grade_fact_unresolved",
        enrollment="",
    )
    target[45:48] = ["enrollment-map-uuid", "migrated", "unexpected-target"]
    result = reconcile_grade_facts(FakeReader([source]), FakeReader([target]), run_id="run-uuid")
    assert result.guard_failures["nonlinked_migrated_enrollment_map"] == 1


def test_digest_is_cross_run_stable_but_expected_enrollment_map_is_checked():
    source = _source_summary()
    first = _target(source, enrollment="random-target-a")
    second = _target(source, enrollment="random-target-b")

    assert first[31] == second[31]
    assert reconcile_grade_facts(FakeReader([source]), FakeReader([second]), run_id="run-uuid").passed

    second[47] = "wrong-target"
    result = reconcile_grade_facts(FakeReader([source]), FakeReader([second]), run_id="run-uuid")
    assert result.guard_failures["enrollment_map_target_mismatch"] == 1


def test_source_hash_must_be_lowercase_hex_and_match_independent_recomputation():
    source = _source_summary()
    target = _target(source)
    target[30] = "c" * 64
    digest = _materialization_digest(target)
    target[31] = target[39] = target[44] = digest

    result = reconcile_grade_facts(
        FakeReader([source]),
        FakeReader([target]),
        run_id="run-uuid",
        source_hashes={("yekun", 1): "a" * 64},
    )
    assert result.source_hash_mismatches == 1

    target[30] = "z" * 64
    digest = _materialization_digest(target)
    target[31] = target[39] = target[44] = digest
    result = reconcile_grade_facts(FakeReader([source]), FakeReader([target]), run_id="run-uuid")
    assert result.guard_failures["source_hash_invalid"] == 1


def test_render_is_aggregate_only_and_contains_no_source_identifiers():
    source = _source_summary()
    result = reconcile_grade_facts(FakeReader([source]), FakeReader([_target(source)]), run_id="run-uuid")
    report = render_grade_fact_reconciliation(result)

    assert "TAM TUTUR" in report
    assert "101" not in report
    assert "journal-x" not in report
    assert "FİN/e-poçt" in report


def test_grade_fact_queries_are_read_only_and_cover_every_non_grade_code():
    assert_read_only(SOURCE_GRADE_FACT_ROWS_SQL)
    assert_read_only(TARGET_GRADE_FACT_ROWS_SQL)
    assert "NOT IN" in SOURCE_GRADE_FACT_ROWS_SQL
    assert "journals_dates_points_archive" in SOURCE_GRADE_FACT_ROWS_SQL
    assert "imthngrscxsblr" in SOURCE_GRADE_FACT_ROWS_SQL
    assert "WHERE id = %s" in TARGET_GRADE_FACT_ROWS_SQL
    assert "p.month_id, '') = 'im2'" in SOURCE_GRADE_FACT_ROWS_SQL
    assert "legacy_mark_conflict" in TARGET_GRADE_FACT_ROWS_SQL
    assert "legacy_mark_unresolved" in TARGET_GRADE_FACT_ROWS_SQL
    assert "'cf:'" in TARGET_GRADE_FACT_ROWS_SQL
    assert "'uf:'" in TARGET_GRADE_FACT_ROWS_SQL
