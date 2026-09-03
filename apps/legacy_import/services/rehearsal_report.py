"""PII-free rehearsal report artifact: determinism payload and atomic writes.

Only the ``deterministic`` section is digested and compared across the two
clean-target rehearsals; ``provenance`` (run/org UUIDs, timestamps, chain
digests that fold the run identity) is reported but never digested.  The
artifact is committed to the repository, so it must never carry raw values,
usernames, emails, per-row digests, file paths, hosts, or database names —
legacy PKs appear only as batch interval endpoints.

Write ritual: the resolved directory must be a real, caller-owned directory
(never a symlink); an existing artifact may only be overwritten when its
stored ``determinism_digest`` equals the incoming one (idempotent rerun); the
bytes land in ``<name>.tmp`` opened with ``O_EXCL | O_NOFOLLOW`` and are
published with ``os.replace``.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import stat
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from .rehearsal_contracts import (
    LegacyRehearsalConfigError,
    LegacyRehearsalError,
    OrderedDigest,
    PhaseBatchRecord,
    PhaseReport,
    RehearsalPolicy,
    canonical_json_digest,
)
from .table_plan import LegacyTablePlan

if TYPE_CHECKING:  # pragma: no cover - annotations only
    from .account_cutover import TargetIdentitySnapshot

REPORT_VERSION = "legacy-rehearsal-report-v1"
DETERMINISM_VERSION = "legacy-rehearsal-determinism-v1"
REPORT_NAME_TEMPLATE = "LEGACY_REHEARSAL_V1_RUN{ordinal}.json"
MIN_REHEARSAL_ORDINAL = 1
MAX_REHEARSAL_ORDINAL = 2
_MAX_REPORT_BYTES = 32 * 1024 * 1024
_READ_CHUNK_BYTES = 1024 * 1024
_BASELINE_DIGEST_NAMESPACE = "legacy-rehearsal-target-baseline-v1"
_REHEARSAL_STATES = ("migrated", "skipped", "quarantined")
_REPORT_TOP_LEVEL_KEYS = frozenset({"determinism_digest", "deterministic", "provenance", "report_version"})
_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")  # mirrors models.TOKEN_PATTERN
_MAX_TOKEN_LENGTH = 64
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

_BASELINE_CODE = "legacy_rehearsal_report_baseline_invalid"
_HISTOGRAM_CODE = "legacy_rehearsal_report_histogram_invalid"
_PAYLOAD_CODE = "legacy_rehearsal_report_payload_invalid"
_PHASE_CODE = "legacy_rehearsal_report_phase_invalid"


def _count(value: object, *, code: str) -> int:
    if type(value) is not int or value < 0:
        raise LegacyRehearsalConfigError(code)
    return value


def _token_text(value: object, *, code: str) -> str:
    if type(value) is not str or len(value) > _MAX_TOKEN_LENGTH or not _TOKEN_PATTERN.fullmatch(value):
        raise LegacyRehearsalConfigError(code)
    return value


def _sha256_text(value: object, *, code: str) -> str:
    if type(value) is not str or not _SHA256_PATTERN.fullmatch(value):
        raise LegacyRehearsalConfigError(code)
    return value


def _mapping(value: object, *, code: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise LegacyRehearsalConfigError(code)
    return value


def target_identity_baseline_digest(snapshot: TargetIdentitySnapshot) -> str:
    """Digest the pre-run canonical identity baseline without exposing keys."""

    row_count = _count(getattr(snapshot, "row_count", None), code=_BASELINE_CODE)
    digest = OrderedDigest(_BASELINE_DIGEST_NAMESPACE)
    digest.advance("row_count", str(row_count))
    for label, attribute in (("username", "usernames"), ("email", "emails")):
        counter = _mapping(getattr(snapshot, attribute, None), code=_BASELINE_CODE)
        try:
            items = sorted(counter.items())
        except TypeError:
            raise LegacyRehearsalConfigError(_BASELINE_CODE) from None
        for key, count in items:
            if type(key) is not str or not key or type(count) is not int or count < 1:
                raise LegacyRehearsalConfigError(_BASELINE_CODE)
            digest.advance(label, key, str(count))
    return digest.hexdigest()


def _batch_entry(batch: object) -> dict[str, object]:
    if not isinstance(batch, PhaseBatchRecord):
        raise LegacyRehearsalConfigError(_PHASE_CODE)
    return {
        "classification_digest": _sha256_text(batch.classification_digest, code=_PHASE_CODE),
        "contract_fingerprint": _sha256_text(batch.contract_fingerprint, code=_PHASE_CODE),
        "entity_type": _token_text(batch.entity_type, code=_PHASE_CODE),
        "first_legacy_pk": _count(batch.first_legacy_pk, code=_PHASE_CODE),
        "last_legacy_pk": _count(batch.last_legacy_pk, code=_PHASE_CODE),
        "migrated_count": _count(batch.migrated_count, code=_PHASE_CODE),
        "quarantined_count": _count(batch.quarantined_count, code=_PHASE_CODE),
        "sequence": _count(batch.sequence, code=_PHASE_CODE),
        "skipped_count": _count(batch.skipped_count, code=_PHASE_CODE),
        "source_digest": _sha256_text(batch.source_digest, code=_PHASE_CODE),
        "source_table": _token_text(batch.source_table, code=_PHASE_CODE),
        "target_digest": _sha256_text(batch.target_digest, code=_PHASE_CODE),
    }


def _validated_state_counts(state_counts: object) -> dict[str, int]:
    validated = {
        _token_text(state, code=_PHASE_CODE): _count(count, code=_PHASE_CODE)
        for state, count in _mapping(state_counts, code=_PHASE_CODE).items()
    }
    return dict(sorted(validated.items()))


def _phase_entry(report: object) -> dict[str, object]:
    if not isinstance(report, PhaseReport):
        raise LegacyRehearsalConfigError(_PHASE_CODE)
    return {
        "batches": [_batch_entry(batch) for batch in report.batches],
        "declared_source_rows": _count(report.declared_source_rows, code=_PHASE_CODE),
        "observed_source_rows": _count(report.observed_source_rows, code=_PHASE_CODE),
        "order": _count(report.order, code=_PHASE_CODE),
        "phase_digest": _sha256_text(report.phase_digest, code=_PHASE_CODE),
        "phase_key": _token_text(report.phase_key, code=_PHASE_CODE),
        "source_tables": [_token_text(table, code=_PHASE_CODE) for table in report.source_tables],
        "staged_account_count": _count(report.staged_account_count, code=_PHASE_CODE),
        "state_counts": _validated_state_counts(report.state_counts),
    }


def _issue_histogram_rows(issue_histogram: object) -> list[dict[str, object]]:
    rows = []
    for key, count in _mapping(issue_histogram, code=_HISTOGRAM_CODE).items():
        if type(key) is not tuple or len(key) != 2:
            raise LegacyRehearsalConfigError(_HISTOGRAM_CODE)
        rows.append(
            {
                "count": _count(count, code=_HISTOGRAM_CODE),
                "rule_code": _token_text(key[0], code=_HISTOGRAM_CODE),
                "severity": _token_text(key[1], code=_HISTOGRAM_CODE),
            }
        )
    rows.sort(key=lambda row: (row["rule_code"], row["severity"]))
    return rows


def build_determinism_payload(
    *,
    plan: LegacyTablePlan,
    phase_registry_fingerprint: str,
    snapshot_sha256: str,
    snapshot_size_bytes: int,
    schema_version: str,
    mode: str,
    accounting_mode: str,
    policy: RehearsalPolicy,
    source_attestation: Mapping[str, object],
    target_guard: Mapping[str, object],
    target_identity_snapshot: TargetIdentitySnapshot,
    phase_reports: Sequence[PhaseReport],
    issue_histogram: Mapping[tuple[str, str], int],
    blocking_issue_count: int,
    credential_field_output_count: int,
    raw_pii_field_output_count: int,
) -> dict[str, object]:
    """Assemble the cross-run-comparable section; run identity never enters it."""

    if not isinstance(plan, LegacyTablePlan) or not isinstance(policy, RehearsalPolicy):
        raise LegacyRehearsalConfigError(_PAYLOAD_CODE)
    if isinstance(phase_reports, (str, bytes)) or not isinstance(phase_reports, Sequence) or not phase_reports:
        raise LegacyRehearsalConfigError(_PAYLOAD_CODE)
    phases = [_phase_entry(report) for report in phase_reports]
    state_totals: Counter[str] = Counter()
    for phase in phases:
        state_totals.update(phase["state_counts"])
    return {
        "accounting_mode": _token_text(accounting_mode, code=_PAYLOAD_CODE),
        "determinism_version": DETERMINISM_VERSION,
        "issue_histogram": _issue_histogram_rows(issue_histogram),
        "mode": _token_text(mode, code=_PAYLOAD_CODE),
        "phase_registry_fingerprint": _sha256_text(phase_registry_fingerprint, code=_PAYLOAD_CODE),
        "phases": phases,
        "plan_fingerprint": _sha256_text(plan.fingerprint, code=_PAYLOAD_CODE),
        "plan_version": _token_text(plan.version, code=_PAYLOAD_CODE),
        "policy": policy.to_safe_log_dict(),
        "schema_version": _token_text(schema_version, code=_PAYLOAD_CODE),
        "snapshot_sha256": _sha256_text(snapshot_sha256, code=_PAYLOAD_CODE),
        "snapshot_size_bytes": _count(snapshot_size_bytes, code=_PAYLOAD_CODE),
        "source_attestation": dict(_mapping(source_attestation, code=_PAYLOAD_CODE)),
        "source_expected_row_count": _count(plan.expected_row_count, code=_PAYLOAD_CODE),
        "source_table_count": len(plan.entries),
        "state_histogram": [{"count": count, "state": state} for state, count in sorted(state_totals.items())],
        "target_guard": dict(_mapping(target_guard, code=_PAYLOAD_CODE)),
        "target_identity_baseline": {
            "digest": target_identity_baseline_digest(target_identity_snapshot),
            "row_count": target_identity_snapshot.row_count,
        },
        "totals": {
            "blocking_issue_count": _count(blocking_issue_count, code=_PAYLOAD_CODE),
            "credential_field_output_count": _count(credential_field_output_count, code=_PAYLOAD_CODE),
            "raw_pii_field_output_count": _count(raw_pii_field_output_count, code=_PAYLOAD_CODE),
            "source_rows": sum(phase["observed_source_rows"] for phase in phases),
            "staged_accounts": sum(phase["staged_account_count"] for phase in phases),
            **{state: state_totals.get(state, 0) for state in _REHEARSAL_STATES},
        },
        "transform_version": _token_text(policy.transform_version(), code=_PAYLOAD_CODE),
    }


def build_report_payload(*, determinism: Mapping[str, object], provenance: Mapping[str, object]) -> dict[str, object]:
    """Seal the deterministic section under its digest beside the provenance."""

    determinism_mapping = _mapping(determinism, code=_PAYLOAD_CODE)
    if determinism_mapping.get("determinism_version") != DETERMINISM_VERSION:
        raise LegacyRehearsalConfigError(_PAYLOAD_CODE)
    provenance_mapping = _mapping(provenance, code=_PAYLOAD_CODE)
    try:
        digest = canonical_json_digest(dict(determinism_mapping))
    except LegacyRehearsalError:
        raise LegacyRehearsalConfigError(_PAYLOAD_CODE) from None
    return {
        "determinism_digest": digest,
        "deterministic": dict(determinism_mapping),
        "provenance": dict(provenance_mapping),
        "report_version": REPORT_VERSION,
    }


def _attested_determinism_digest(document: object, *, mismatch_code: str) -> str:
    """Validate the full report shape and prove the stored digest is honest."""

    mapping = _mapping(document, code=_PAYLOAD_CODE)
    if set(mapping.keys()) != _REPORT_TOP_LEVEL_KEYS or mapping.get("report_version") != REPORT_VERSION:
        raise LegacyRehearsalConfigError(_PAYLOAD_CODE)
    deterministic = _mapping(mapping.get("deterministic"), code=_PAYLOAD_CODE)
    if deterministic.get("determinism_version") != DETERMINISM_VERSION:
        raise LegacyRehearsalConfigError(_PAYLOAD_CODE)
    _mapping(mapping.get("provenance"), code=_PAYLOAD_CODE)
    stored = _sha256_text(mapping.get("determinism_digest"), code=_PAYLOAD_CODE)
    try:
        computed = canonical_json_digest(dict(deterministic))
    except LegacyRehearsalError:
        raise LegacyRehearsalConfigError(_PAYLOAD_CODE) from None
    if not hmac.compare_digest(stored, computed):
        raise LegacyRehearsalConfigError(mismatch_code)
    return stored


def _validated_report_dir(report_dir: object) -> str:
    if type(report_dir) is not str or not report_dir:
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_dir_invalid")
    try:
        dir_stat = os.lstat(report_dir)
    except OSError:
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_dir_invalid") from None
    if stat.S_ISLNK(dir_stat.st_mode) or not stat.S_ISDIR(dir_stat.st_mode) or dir_stat.st_uid != os.getuid():
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_dir_invalid")
    return report_dir


def _assert_overwrite_allowed(path: str, digest: str) -> None:
    try:
        existing_stat = os.lstat(path)
    except FileNotFoundError:
        return
    except OSError:
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_conflict") from None
    if not stat.S_ISREG(existing_stat.st_mode):
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_conflict")
    try:
        existing_digest = read_report_determinism_digest(path)
    except LegacyRehearsalError:
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_conflict") from None
    if not hmac.compare_digest(existing_digest, digest):
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_conflict")


def _serialized_report(payload: Mapping[str, object]) -> bytes:
    try:
        document = json.dumps(dict(payload), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    except Exception:
        raise LegacyRehearsalConfigError(_PAYLOAD_CODE) from None
    return (document + "\n").encode("ascii")


def _atomic_publish(path: str, content: bytes) -> None:
    tmp_path = path + ".tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        file_descriptor = os.open(tmp_path, flags, 0o600)
    except OSError:
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_write_failed") from None
    try:
        view = memoryview(content)
        while view:
            view = view[os.write(file_descriptor, view) :]
        os.fsync(file_descriptor)
        os.fchmod(file_descriptor, 0o644)
        os.close(file_descriptor)
        os.replace(tmp_path, path)
    except OSError:
        for cleanup in (lambda: os.close(file_descriptor), lambda: os.unlink(tmp_path)):
            try:
                cleanup()
            except OSError:
                pass
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_write_failed") from None


def write_report(*, report_dir: str, ordinal: int, payload: Mapping[str, object]) -> str:
    """Atomically publish one report; overwrite only an equal-digest rerun."""

    if type(ordinal) is not int or not MIN_REHEARSAL_ORDINAL <= ordinal <= MAX_REHEARSAL_ORDINAL:
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_ordinal_invalid")
    digest = _attested_determinism_digest(payload, mismatch_code=_PAYLOAD_CODE)
    path = os.path.join(_validated_report_dir(report_dir), REPORT_NAME_TEMPLATE.format(ordinal=ordinal))
    _assert_overwrite_allowed(path, digest)
    _atomic_publish(path, _serialized_report(payload))
    return path


def read_report_determinism_digest(path: str) -> str:
    """Return a stored digest only after re-proving it against the content."""

    if type(path) is not str or not path:
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_unreadable")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        file_descriptor = os.open(path, flags)
    except OSError:
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_unreadable") from None
    try:
        file_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > _MAX_REPORT_BYTES:
            raise LegacyRehearsalConfigError("legacy_rehearsal_report_unreadable")
        chunks = []
        while True:
            chunk = os.read(file_descriptor, _READ_CHUNK_BYTES)
            if not chunk:
                break
            chunks.append(chunk)
    except OSError:
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_unreadable") from None
    finally:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
    try:
        document = json.loads(b"".join(chunks).decode("ascii"))
    except Exception:
        raise LegacyRehearsalConfigError(_PAYLOAD_CODE) from None
    return _attested_determinism_digest(document, mismatch_code="legacy_rehearsal_report_digest_invalid")
