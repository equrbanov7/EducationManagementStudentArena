import hashlib
import json
import os
import pathlib
from types import SimpleNamespace

import pytest

from apps.legacy_import.services.rehearsal_contracts import (
    DEFAULT_BATCH_ROWS,
    EmailTrustPolicy,
    LegacyRehearsalConfigError,
    PhaseBatchRecord,
    PhaseReport,
    RehearsalPolicy,
    StudentIdentifierPolicy,
    UsernamePolicy,
    canonical_json_digest,
)
from apps.legacy_import.services.rehearsal_report import (
    DETERMINISM_VERSION,
    REPORT_NAME_TEMPLATE,
    REPORT_VERSION,
    build_determinism_payload,
    build_report_payload,
    read_report_determinism_digest,
    target_identity_baseline_digest,
    write_report,
)
from apps.legacy_import.services.table_plan import load_legacy_table_plan

_SENTINEL_USERNAME = "john.doe"
_SENTINEL_EMAIL = "john@example.test"


def _hex(seed):
    return hashlib.sha256(seed.encode("ascii")).hexdigest()


def _policy(**overrides):
    values = {
        "phase_keys": ("identity_cohort",),
        "username_policy": UsernamePolicy.LEGACY_KEY,
        "student_identifier_policy": StudentIdentifierPolicy.LEGACY_PK,
        "email_trust_policy": EmailTrustPolicy.DENY_ALL,
        "email_trust_manifest_digest": "",
        "batch_rows": DEFAULT_BATCH_ROWS,
        "source_chunk_size": 1_000,
        "max_staged_accounts": 0,
        "student_role_name": "",
        "worker_role_name": "",
    }
    values.update(overrides)
    return RehearsalPolicy(**values)


def _snapshot(**overrides):
    values = {
        "usernames": {_SENTINEL_USERNAME: 1, "jane.roe": 2},
        "emails": {_SENTINEL_EMAIL: 1},
        "row_count": 3,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _batch(**overrides):
    values = {
        "source_table": "students",
        "entity_type": "student",
        "sequence": 1,
        "first_legacy_pk": 1,
        "last_legacy_pk": 1000,
        "migrated_count": 0,
        "skipped_count": 990,
        "quarantined_count": 10,
        "contract_fingerprint": _hex("contract-students"),
        "source_digest": _hex("source-students-1"),
        "classification_digest": _hex("classification-students-1"),
        "target_digest": _hex("target-students-1"),
    }
    values.update(overrides)
    return PhaseBatchRecord(**values)


def _phase_report(**overrides):
    values = {
        "phase_key": "identity_cohort",
        "order": 20,
        "source_tables": ("students", "workers"),
        "declared_source_rows": 1729,
        "observed_source_rows": 1729,
        "batches": (
            _batch(),
            _batch(
                source_table="workers",
                entity_type="worker",
                first_legacy_pk=1,
                last_legacy_pk=729,
                skipped_count=729,
                quarantined_count=0,
                contract_fingerprint=_hex("contract-workers"),
                source_digest=_hex("source-workers-1"),
                classification_digest=_hex("classification-workers-1"),
                target_digest=_hex("target-workers-1"),
            ),
        ),
        "state_counts": {"skipped": 1719, "quarantined": 10},
        "issue_counts": {},
        "staged_account_count": 0,
        "phase_digest": _hex("phase-identity-cohort"),
    }
    values.update(overrides)
    return PhaseReport(**values)


def _determinism(**overrides):
    plan = load_legacy_table_plan()
    values = {
        "plan": plan,
        "phase_registry_fingerprint": _hex("phase-registry"),
        "snapshot_sha256": _hex("snapshot"),
        "snapshot_size_bytes": 2_142_912_818,
        "schema_version": f"{plan.version}.{plan.fingerprint[:12]}",
        "mode": "rehearsal",
        "accounting_mode": "batch",
        "policy": _policy(),
        "source_attestation": {
            "attestation_version": "legacy-source-attestation-v1",
            "contracts": [],
            "status": "passed",
        },
        "target_guard": {"database_name_shape": "emsarena_rehearsal_<12hex>", "vendor": "postgresql"},
        "target_identity_snapshot": _snapshot(),
        "phase_reports": (_phase_report(),),
        "issue_histogram": {("legacy_account_email_untrusted", "info"): 1719},
        "blocking_issue_count": 0,
        "credential_field_output_count": 0,
        "raw_pii_field_output_count": 0,
    }
    values.update(overrides)
    return build_determinism_payload(**values)


def _provenance(**overrides):
    values = {
        "run_id": "0b0e9c1a-1111-4222-8333-444455556666",
        "organization_id": "9f8e7d6c-1111-4222-8333-444455556666",
        "rehearsal_ordinal": 1,
        "status": "succeeded",
        "failure_code": "",
        "started_at": "2026-08-25T10:00:00Z",
        "finished_at": "2026-08-25T10:05:00Z",
        "batch_chain_digests": [{"last_chain_digest": _hex("chain-students"), "source_table": "students"}],
    }
    values.update(overrides)
    return values


def _report(**overrides):
    return build_report_payload(determinism=_determinism(), provenance=_provenance(), **overrides)


def _write(tmp_path, payload=None, ordinal=1):
    resolved = (
        payload if payload is not None else build_report_payload(determinism=_determinism(), provenance=_provenance())
    )
    return write_report(report_dir=str(tmp_path), ordinal=ordinal, payload=resolved), resolved


def _collect_keys(value, keys):
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(key)
            _collect_keys(nested, keys)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _collect_keys(nested, keys)
    return keys


def _code(callable_object, *args, **kwargs):
    with pytest.raises(LegacyRehearsalConfigError) as failure:
        callable_object(*args, **kwargs)
    return failure.value.code


# ---------------------------------------------------------------------------
# Determinism payload
# ---------------------------------------------------------------------------


def test_determinism_digest_excludes_run_and_timestamps():
    first = build_report_payload(determinism=_determinism(), provenance=_provenance())
    second = build_report_payload(
        determinism=_determinism(),
        provenance=_provenance(
            run_id="ffffffff-0000-4000-8000-000000000000",
            started_at="2026-08-26T09:00:00Z",
            finished_at="2026-08-26T09:07:00Z",
            rehearsal_ordinal=2,
        ),
    )
    assert first["determinism_digest"] == second["determinism_digest"]
    assert first["deterministic"] == second["deterministic"]
    deterministic_keys = _collect_keys(first["deterministic"], set())
    for forbidden in (
        "run_id",
        "organization_id",
        "started_at",
        "finished_at",
        "rehearsal_ordinal",
        "batch_chain_digests",
    ):
        assert forbidden not in deterministic_keys


def test_determinism_digest_changes_when_a_batch_digest_changes():
    baseline = _determinism()
    drifted = _determinism(
        phase_reports=(
            _phase_report(
                batches=(
                    _batch(source_digest=_hex("source-students-1-drift")),
                    _phase_report().batches[1],
                )
            ),
        )
    )
    assert canonical_json_digest(baseline) != canonical_json_digest(drifted)


def test_determinism_payload_aggregates_states_and_totals():
    payload = _determinism()
    assert payload["determinism_version"] == DETERMINISM_VERSION
    assert payload["plan_version"] == "legacy-table-plan-v1"
    assert payload["source_table_count"] == 81
    assert payload["source_expected_row_count"] == 9_044_531
    assert payload["state_histogram"] == [
        {"count": 10, "state": "quarantined"},
        {"count": 1719, "state": "skipped"},
    ]
    assert payload["issue_histogram"] == [
        {"count": 1719, "rule_code": "legacy_account_email_untrusted", "severity": "info"}
    ]
    assert payload["totals"] == {
        "blocking_issue_count": 0,
        "credential_field_output_count": 0,
        "migrated": 0,
        "quarantined": 10,
        "raw_pii_field_output_count": 0,
        "skipped": 1719,
        "source_rows": 1729,
        "staged_accounts": 0,
    }
    assert payload["transform_version"] == _policy().transform_version()
    assert payload["target_identity_baseline"] == {
        "digest": target_identity_baseline_digest(_snapshot()),
        "row_count": 3,
    }


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"phase_reports": ()}, "legacy_rehearsal_report_payload_invalid"),
        ({"phase_reports": ("not-a-phase",)}, "legacy_rehearsal_report_phase_invalid"),
        ({"snapshot_sha256": "not-hex"}, "legacy_rehearsal_report_payload_invalid"),
        ({"snapshot_size_bytes": -1}, "legacy_rehearsal_report_payload_invalid"),
        ({"mode": "Rehearsal!"}, "legacy_rehearsal_report_payload_invalid"),
        ({"source_attestation": None}, "legacy_rehearsal_report_payload_invalid"),
        ({"issue_histogram": {"flat-key": 1}}, "legacy_rehearsal_report_histogram_invalid"),
        ({"issue_histogram": {("rule", "info"): -1}}, "legacy_rehearsal_report_histogram_invalid"),
        ({"blocking_issue_count": True}, "legacy_rehearsal_report_payload_invalid"),
        (
            {"target_identity_snapshot": SimpleNamespace(usernames={}, emails={}, row_count=-1)},
            "legacy_rehearsal_report_baseline_invalid",
        ),
    ],
)
def test_determinism_payload_fails_closed_on_malformed_inputs(overrides, code):
    assert _code(_determinism, **overrides) == code


def test_phase_entry_rejects_malformed_state_counts_and_digests():
    assert (
        _code(_determinism, phase_reports=(_phase_report(state_counts={"skipped": -1}),))
        == "legacy_rehearsal_report_phase_invalid"
    )
    assert (
        _code(_determinism, phase_reports=(_phase_report(phase_digest="short"),))
        == "legacy_rehearsal_report_phase_invalid"
    )
    assert (
        _code(_determinism, phase_reports=(_phase_report(batches=(_batch(first_legacy_pk="1"),)),))
        == "legacy_rehearsal_report_phase_invalid"
    )


def test_target_identity_baseline_digest_is_order_independent_and_content_sensitive():
    forward = _snapshot(usernames={"a.a": 1, "b.b": 2}, emails={"a@x.test": 1}, row_count=3)
    reversed_order = _snapshot(usernames={"b.b": 2, "a.a": 1}, emails={"a@x.test": 1}, row_count=3)
    drifted = _snapshot(usernames={"a.a": 1, "b.b": 3}, emails={"a@x.test": 1}, row_count=3)
    assert target_identity_baseline_digest(forward) == target_identity_baseline_digest(reversed_order)
    assert target_identity_baseline_digest(forward) != target_identity_baseline_digest(drifted)
    assert len(target_identity_baseline_digest(forward)) == 64
    for broken in (
        _snapshot(usernames={"": 1}),
        _snapshot(usernames={"a.a": 0}),
        _snapshot(usernames={1: 1}),
        _snapshot(emails=None),
        _snapshot(row_count="3"),
    ):
        assert _code(target_identity_baseline_digest, broken) == "legacy_rehearsal_report_baseline_invalid"


def test_build_report_payload_seals_the_deterministic_section():
    payload = _report()
    assert payload["report_version"] == REPORT_VERSION
    assert payload["determinism_digest"] == canonical_json_digest(payload["deterministic"])
    assert _code(build_report_payload, determinism={"determinism_version": "wrong"}, provenance={}) == (
        "legacy_rehearsal_report_payload_invalid"
    )
    assert _code(
        build_report_payload,
        determinism={"determinism_version": DETERMINISM_VERSION, "value": object()},
        provenance={},
    ) == ("legacy_rehearsal_report_payload_invalid")


# ---------------------------------------------------------------------------
# Atomic write ritual
# ---------------------------------------------------------------------------


def test_report_write_is_idempotent_for_identical_determinism(tmp_path):
    path, payload = _write(tmp_path)
    assert path == str(tmp_path / REPORT_NAME_TEMPLATE.format(ordinal=1))
    first_content = pathlib.Path(path).read_text(encoding="ascii")
    rewritten_path, _ = _write(tmp_path, payload=payload)
    assert rewritten_path == path
    assert pathlib.Path(path).read_text(encoding="ascii") == first_content
    # A regenerated report with new provenance but an equal digest also lands.
    regenerated = build_report_payload(
        determinism=_determinism(),
        provenance=_provenance(finished_at="2026-08-26T11:00:00Z"),
    )
    _write(tmp_path, payload=regenerated)
    document = json.loads(pathlib.Path(path).read_text(encoding="ascii"))
    assert document["provenance"]["finished_at"] == "2026-08-26T11:00:00Z"
    assert not os.path.exists(path + ".tmp")
    assert read_report_determinism_digest(path) == payload["determinism_digest"]


def test_report_write_refuses_conflicting_overwrite(tmp_path):
    _write(tmp_path)
    conflicting = build_report_payload(
        determinism=_determinism(snapshot_size_bytes=2_142_912_819),
        provenance=_provenance(),
    )
    assert (
        _code(write_report, report_dir=str(tmp_path), ordinal=1, payload=conflicting)
        == "legacy_rehearsal_report_conflict"
    )
    # The refused write must not disturb the existing artifact.
    stored = json.loads((tmp_path / REPORT_NAME_TEMPLATE.format(ordinal=1)).read_text(encoding="ascii"))
    assert stored["deterministic"]["snapshot_size_bytes"] == 2_142_912_818


def test_report_contains_no_username_email_or_path(tmp_path):
    path, _ = _write(tmp_path)
    document = pathlib.Path(path).read_text(encoding="ascii")
    assert _SENTINEL_USERNAME not in document
    assert _SENTINEL_EMAIL not in document
    assert "@" not in document
    assert str(tmp_path) not in document
    assert "emsarena_rehearsal_<12hex>" in document  # only the shape token, never a real name


def test_report_write_refuses_symlinked_directory(tmp_path):
    real_directory = tmp_path / "reports"
    real_directory.mkdir()
    link = tmp_path / "reports-link"
    link.symlink_to(real_directory)
    assert (
        _code(write_report, report_dir=str(link), ordinal=1, payload=_report()) == "legacy_rehearsal_report_dir_invalid"
    )
    assert list(real_directory.iterdir()) == []


def test_report_write_validates_directory_ordinal_and_payload(tmp_path):
    payload = _report()
    regular_file = tmp_path / "not-a-directory"
    regular_file.write_text("x")
    for report_dir in (str(regular_file), str(tmp_path / "missing"), "", None):
        assert _code(write_report, report_dir=report_dir, ordinal=1, payload=payload) == (
            "legacy_rehearsal_report_dir_invalid"
        )
    for ordinal in (0, 3, True, "1", None):
        assert _code(write_report, report_dir=str(tmp_path), ordinal=ordinal, payload=payload) == (
            "legacy_rehearsal_report_ordinal_invalid"
        )
    tampered = dict(payload)
    tampered["determinism_digest"] = _hex("not-the-digest")
    for broken in (None, {}, {**payload, "extra": 1}, tampered):
        assert _code(write_report, report_dir=str(tmp_path), ordinal=1, payload=broken) == (
            "legacy_rehearsal_report_payload_invalid"
        )


def test_report_write_refuses_stale_tmp_and_symlinked_target(tmp_path):
    payload = _report()
    name = REPORT_NAME_TEMPLATE.format(ordinal=1)
    stale = tmp_path / (name + ".tmp")
    stale.write_text("stale")
    assert (
        _code(write_report, report_dir=str(tmp_path), ordinal=1, payload=payload)
        == "legacy_rehearsal_report_write_failed"
    )
    stale.unlink()
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text("{}")
    (tmp_path / name).symlink_to(elsewhere)
    assert (
        _code(write_report, report_dir=str(tmp_path), ordinal=1, payload=payload) == "legacy_rehearsal_report_conflict"
    )


def test_read_report_digest_reproves_the_stored_digest(tmp_path):
    path, payload = _write(tmp_path)
    assert read_report_determinism_digest(path) == payload["determinism_digest"]
    assert _code(read_report_determinism_digest, str(tmp_path / "missing.json")) == (
        "legacy_rehearsal_report_unreadable"
    )
    garbage = tmp_path / "garbage.json"
    garbage.write_text("not json")
    assert _code(read_report_determinism_digest, str(garbage)) == "legacy_rehearsal_report_payload_invalid"
    document = json.loads(pathlib.Path(path).read_text(encoding="ascii"))
    document["deterministic"]["snapshot_size_bytes"] += 1  # tamper without refreshing the digest
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
    assert _code(read_report_determinism_digest, str(tampered)) == "legacy_rehearsal_report_digest_invalid"


def test_written_report_has_the_expected_permissions_and_shape(tmp_path):
    path, payload = _write(tmp_path, ordinal=2)
    assert path.endswith("LEGACY_REHEARSAL_V1_RUN2.json")
    assert os.stat(path).st_mode & 0o777 == 0o644
    document = json.loads(pathlib.Path(path).read_text(encoding="ascii"))
    assert set(document) == {"determinism_digest", "deterministic", "provenance", "report_version"}
    assert document == json.loads(json.dumps(payload))
