"""Bal-vərəqi immutable artifact uzlaşdırmasının bazasız testləri."""

import hashlib
import zlib

from scripts.legacy_reconcile.grade_artifacts import (
    SOURCE_ARTIFACT_ROWS_SQL,
    TARGET_ARTIFACT_ROWS_SQL,
    _materialization_digest,
    _source_row,
    reconcile_grade_artifacts,
    render_grade_artifact_reconciliation,
)
from scripts.legacy_reconcile.transport import assert_read_only


class FakeReader:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def query(self, label, sql, params=None):
        self.calls.append((label, sql, params))
        return list(self.rows)


def _source(payload=b"<table><td>test-only</td></table>"):
    return [
        "1",
        "17",
        "journal-x",
        "2023-08-14 10:00:00",
        hashlib.sha256(payload).hexdigest(),
        str(len(payload)),
    ]


def _target(source, payload=b"<table><td>test-only</td></table>"):
    normalized = _source_row(source)
    row = [
        normalized[0],
        normalized[1],
        normalized[2],
        normalized[3],
        normalized[4],
        normalized[5],
        zlib.compress(payload, 9),
        normalized[6],
        "",
        "b" * 64,
        "rehearsal-identity-v1.test",
        "artifact-uuid",
        True,
        "score_sheet_export",
        "myedu_mariadb",
        "balvereqi_logs",
        "map-uuid",
        "migrated",
        "registrar.legacygradeartifact",
        "artifact-uuid",
        "",
        "observation-uuid",
        "migrated",
        "registrar.legacygradeartifact",
        "artifact-uuid",
        "",
    ]
    digest = _materialization_digest(row)
    row[8] = row[20] = row[25] = digest
    return row


def test_artifact_reconciliation_checks_metadata_hash_size_zlib_and_ledger():
    payload = b"<table><td>test-only</td></table>"
    source = _source(payload)
    target = _target(source, payload)

    result = reconcile_grade_artifacts(FakeReader([source]), FakeReader([target]), run_id="run-uuid")

    assert result.passed
    assert result.source_rows == result.target_rows == 1
    assert result.source_payload_bytes == result.target_payload_bytes == len(payload)


def test_artifact_reconciliation_detects_corruption_hash_drift_and_missing_keys():
    source = _source()
    target = _target(source)
    target[6] = zlib.compress(b"different", 9)
    target[7] = "c" * 64
    digest = _materialization_digest(target)
    target[8] = target[20] = target[25] = digest

    result = reconcile_grade_artifacts(FakeReader([source]), FakeReader([target]), run_id="run-uuid")

    assert not result.passed
    assert result.source_hash_mismatches == 1
    assert result.guard_failures["compressed_payload_invalid"] == 1

    missing = reconcile_grade_artifacts(FakeReader([source]), FakeReader([]), run_id="run-uuid")
    assert missing.missing_keys == 1


def test_artifact_report_is_aggregate_only_and_queries_are_read_only():
    source = _source()
    result = reconcile_grade_artifacts(FakeReader([source]), FakeReader([_target(source)]), run_id="run-uuid")
    report = render_grade_artifact_reconciliation(result)

    assert "TAM TUTUR" in report
    assert "journal-x" not in report
    assert "test-only" not in report
    assert_read_only(SOURCE_ARTIFACT_ROWS_SQL)
    assert_read_only(TARGET_ARTIFACT_ROWS_SQL)
    assert "WHERE id = %s" in TARGET_ARTIFACT_ROWS_SQL
