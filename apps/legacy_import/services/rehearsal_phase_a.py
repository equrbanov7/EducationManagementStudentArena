"""Phase A: everything a rehearsal must prove before it may write one row.

The whole sequence is read-only.  It attests the fixed table plan and the phase
registry, refuses a target database that is not provably disposable, pins the
session to an explicit tenant context (never ``bypass_rls``), streams the source
snapshot preflight, attests both audited identity contracts and finally refuses
a scope that a terminal run already consumed (SPEC D5).  The assembled payload
carries digests, counters and shape tokens only — no path, host, database name
or actor identity — so it can be digested into the committed report artifact.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from apps.legacy_import.models import LegacyMigrationRun
from core.rls import set_rls_tenant

from .account_cutover import TargetIdentitySnapshot, load_target_identity_snapshot
from .mariadb_gateway import build_configured_mariadb_source_factory, load_mariadb_source_config
from .rehearsal_contracts import (
    SOURCE_SYSTEM,
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    RehearsalPhase,
    RehearsalPolicy,
    canonical_json_digest,
    compute_phase_registry_fingerprint,
    load_rehearsal_phase_registry,
)
from .rehearsal_report import target_identity_baseline_digest
from .rehearsal_target_guard import TargetGuardAttestation, assert_disposable_rehearsal_target
from .source_attestation import attest_legacy_identity_source
from .table_plan import EXPECTED_TABLE_COUNT, SOURCE_SNAPSHOT_SHA256, TABLE_PLAN_VERSION, load_legacy_table_plan

# The rehearsal scope is sealed here: a cutover mode is structurally unreachable
# and row accounting is always the batch chain.
# Plain text, not the ``TextChoices`` member: these values are digested and the
# report validator accepts exact ``str`` only.
RUN_MODE = str(LegacyMigrationRun.Mode.REHEARSAL)
ACCOUNTING_MODE = str(LegacyMigrationRun.AccountingMode.BATCH)
_TERMINAL_STATUSES = (
    LegacyMigrationRun.Status.SUCCEEDED,
    LegacyMigrationRun.Status.FAILED,
    LegacyMigrationRun.Status.CANCELLED,
)
_CONTRACT_SOURCE_TABLES = {"student_identity": "students", "worker_identity": "workers"}


@dataclass(frozen=True)
class PhaseAAttestation:
    """Immutable Phase A evidence; the run lifecycle consumes nothing else."""

    plan: Any
    phases: tuple[RehearsalPhase, ...]
    phase_registry_fingerprint: str
    guard: TargetGuardAttestation
    snapshot_sha256: str
    snapshot_size_bytes: int
    schema_version: str
    source_attestation: dict[str, object]
    source_factory: Callable[[], Any]
    source_row_count: int
    credential_field_output_count: int
    baseline: TargetIdentitySnapshot
    policy: RehearsalPolicy

    def transform_version(self) -> str:
        return self.policy.transform_version()


def default_source_factory(settings_object: object):
    """Build the audited MariaDB factory from opt-in settings only."""

    return build_configured_mariadb_source_factory(load_mariadb_source_config(settings_object))


def select_phases(policy: RehearsalPolicy) -> tuple[RehearsalPhase, ...]:
    """Resolve the policy's phase keys against the fingerprint-attested registry."""

    registry = load_rehearsal_phase_registry()
    selected_keys = set(policy.phase_keys)
    if not selected_keys.issubset({phase.phase_key for phase in registry}):
        raise LegacyRehearsalConfigError("legacy_rehearsal_phase_key_unknown")
    return tuple(phase for phase in registry if phase.phase_key in selected_keys)


def _assert_source_attestation(attestation: object, *, plan) -> int:
    """A8: the attestation must be complete, row-exact and credential-free."""

    if not isinstance(attestation, Mapping) or attestation.get("status") != "passed":
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_attestation_invalid")
    contracts = attestation.get("contracts")
    if isinstance(contracts, (str, bytes)) or not isinstance(contracts, Sequence) or not contracts:
        raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_attestation_invalid")
    credential_total = 0
    for report in contracts:
        if not isinstance(report, Mapping):
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_attestation_invalid")
        if report.get("credential_field_output_count") != 0:
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_credential_field_detected")
        source_table = _CONTRACT_SOURCE_TABLES.get(report.get("contract_key"))
        if source_table is None:
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_attestation_invalid")
        if report.get("projected_row_count") != plan.entry_for(source_table).expected_rows:
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_source_attestation_row_mismatch")
    return credential_total


def terminal_run_exists(*, organization, snapshot_sha256: str, transform_version: str) -> bool:
    """D5: one rehearsal per disposable target database."""

    return LegacyMigrationRun.objects.filter(
        organization=organization,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=snapshot_sha256,
        transform_version=transform_version,
        status__in=_TERMINAL_STATUSES,
    ).exists()


def attest_phase_a(
    *,
    settings_object: object,
    policy: RehearsalPolicy,
    organization: object,
    source_path: str,
    source_size_bytes: int,
    source_preflight: Callable[..., Any],
    source_factory_builder: Callable[[object], Any],
    enforce_scope_precheck: bool = True,
) -> PhaseAAttestation:
    """Run the complete Phase A sequence (A2-A10); it writes nothing at all.

    ``enforce_scope_precheck`` is disabled only for a report regeneration, which
    re-reads a run that has already consumed its scope on purpose (SPEC D5 bars
    a *second* rehearsal, not re-emitting the first one's artifact).
    """

    if not isinstance(policy, RehearsalPolicy):
        raise LegacyRehearsalConfigError("legacy_rehearsal_policy_invalid")
    if organization is None or getattr(organization, "pk", None) is None:
        raise LegacyRehearsalConfigError("legacy_rehearsal_organization_invalid")
    plan = load_legacy_table_plan()
    phases = select_phases(policy)
    guard = assert_disposable_rehearsal_target(settings_object=settings_object)
    set_rls_tenant(organization.pk, local=False)
    preflight = source_preflight(
        source=source_path,
        expected_sha256=SOURCE_SNAPSHOT_SHA256,
        expected_size_bytes=source_size_bytes,
        expected_table_count=EXPECTED_TABLE_COUNT,
    )
    source_factory = source_factory_builder(settings_object)
    attestation = attest_legacy_identity_source(connection_factory=source_factory)
    credential_total = _assert_source_attestation(attestation, plan=plan)
    if enforce_scope_precheck and terminal_run_exists(
        organization=organization,
        snapshot_sha256=preflight.digest,
        transform_version=policy.transform_version(),
    ):
        raise LegacyRehearsalConfigError("legacy_rehearsal_scope_already_completed")
    return PhaseAAttestation(
        plan=plan,
        phases=phases,
        phase_registry_fingerprint=compute_phase_registry_fingerprint(phases, plan=plan),
        guard=guard,
        snapshot_sha256=preflight.digest,
        snapshot_size_bytes=preflight.size,
        schema_version=f"{TABLE_PLAN_VERSION}.{plan.fingerprint[:12]}",
        source_attestation=dict(attestation),
        source_factory=source_factory,
        source_row_count=sum(phase.declared_source_rows(plan) for phase in phases),
        credential_field_output_count=credential_total,
        baseline=load_target_identity_snapshot(),
        policy=policy,
    )


def attestation_payload(attested: PhaseAAttestation, *, baseline=None) -> dict[str, object]:
    """Assemble the PII-free Phase A evidence bound into the ledger by B3."""

    return {
        "accounting_mode": ACCOUNTING_MODE,
        "mode": RUN_MODE,
        "phase_keys": [phase.phase_key for phase in attested.phases],
        "phase_registry_fingerprint": attested.phase_registry_fingerprint,
        "plan_fingerprint": attested.plan.fingerprint,
        "plan_version": attested.plan.version,
        "policy": attested.policy.to_safe_log_dict(),
        "schema_version": attested.schema_version,
        "snapshot_sha256": attested.snapshot_sha256,
        "snapshot_size_bytes": attested.snapshot_size_bytes,
        "source_attestation": attested.source_attestation,
        "source_expected_row_count": attested.plan.expected_row_count,
        "source_row_count": attested.source_row_count,
        "source_table_count": len(attested.plan.entries),
        "target_guard": attested.guard.to_safe_log_dict(),
        "target_identity_baseline": {
            "digest": target_identity_baseline_digest(baseline if baseline is not None else attested.baseline),
            "row_count": (baseline if baseline is not None else attested.baseline).row_count,
        },
        "transform_version": attested.policy.transform_version(),
    }


def attestation_digest(payload: Mapping[str, object]) -> str:
    """Digest the Phase A payload; the result is the B3 issue's payload digest."""

    return canonical_json_digest(payload)


__all__ = [
    "ACCOUNTING_MODE",
    "RUN_MODE",
    "PhaseAAttestation",
    "attest_phase_a",
    "attestation_digest",
    "attestation_payload",
    "default_source_factory",
    "select_phases",
    "terminal_run_exists",
]
