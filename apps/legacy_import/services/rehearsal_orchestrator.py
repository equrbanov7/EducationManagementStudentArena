"""Run lifecycle, phase driving and the terminal report publication.

Phase A evidence comes from ``rehearsal_phase_a`` and Phase C evidence from
``rehearsal_reconciliation``; this module owns only what sits between them: the
run scope (create/start/resume), the ordered phase drive, and the fail-closed
terminal transition followed by the atomic report write.

Interrupt semantics: a cancellation or a source-transport interruption is
re-raised untouched, so the run stays ``RUNNING`` and remains resumable through
``--resume-run-id``.  A terminal evidence failure finishes the run ``FAILED``
first, so the ledger records why a fresh disposable target is required.  This
module never calls ``core.rls.bypass_rls``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from django.db import connection as default_connection

from apps.legacy_import.models import LegacyMigrationRun
from core.rls import set_rls_tenant

from .ledger import create_run, finish_run, start_run, upsert_issue
from .preflight import inspect_legacy_source
from .rehearsal_authorizer import build_rehearsal_authorizer, build_target_validators
from .rehearsal_contracts import (
    SOURCE_SYSTEM,
    LegacyRehearsalConfigError,
    LegacyRehearsalEvidenceError,
    LegacyRehearsalResumeError,
    PhaseReport,
    RehearsalContext,
    RehearsalPolicy,
    canonical_json_digest,
)
from .rehearsal_identity_phase import ISSUE_SEVERITY, build_email_trust_policy, rebase_target_snapshot_for_run
from .rehearsal_phase_a import (
    ACCOUNTING_MODE,
    RUN_MODE,
    PhaseAAttestation,
    attest_phase_a,
    attestation_digest,
    attestation_payload,
    default_source_factory,
)
from .rehearsal_reconciliation import (
    issue_evidence,
    normalized_phase_report,
    phase_report_from_ledger,
    provenance_payload,
    reconcile_run,
)
from .rehearsal_report import (
    build_determinism_payload,
    build_report_payload,
    read_report_determinism_digest,
    write_report,
)
from .rehearsal_target_guard import assert_disposable_rehearsal_target

ATTESTATION_RULE_CODE = "legacy_rehearsal_attestation"
ATTESTATION_SOURCE_TABLE = "rehearsal"
ATTESTATION_ENTITY_TYPE = "attestation"
ATTESTATION_LEGACY_PK = "phase-a"
BLOCKING_ISSUE_FAILURE_CODE = "legacy_rehearsal_blocking_issue"
DETERMINISM_MISMATCH_CODE = "legacy_rehearsal_determinism_mismatch"
CANCELLED_FAILURE_CODE = "legacy_rehearsal_cancelled"
# The artifact is assembled from digests and counters only, so the run emits no
# raw field at all; the payload records that as an explicitly checkable zero.
RAW_PII_FIELD_OUTPUT_COUNT = 0


@dataclass(frozen=True)
class RehearsalOutcome:
    """Sanitized result of one rehearsal attempt; ``payload`` is stdout-safe."""

    run_id: object
    status: str
    failure_code: str
    determinism_digest: str
    report_path: str
    payload: dict[str, object]


def _assert_actor(actor: object) -> None:
    if actor is None or getattr(actor, "pk", None) is None or not getattr(actor, "is_active", False):
        raise LegacyRehearsalConfigError("legacy_rehearsal_actor_invalid")


def plan_rehearsal(
    *,
    settings_object: object,
    policy: RehearsalPolicy,
    organization: object,
    actor: object,
    source_path: str,
    source_size_bytes: int,
    source_preflight: Callable[..., Any] = inspect_legacy_source,
    source_factory_builder: Callable[[object], Any] = default_source_factory,
) -> dict[str, object]:
    """Run Phase A only: no run row, no ledger write, no report artifact."""

    _assert_actor(actor)
    attested = attest_phase_a(
        settings_object=settings_object,
        policy=policy,
        organization=organization,
        source_path=source_path,
        source_size_bytes=source_size_bytes,
        source_preflight=source_preflight,
        source_factory_builder=source_factory_builder,
    )
    payload = attestation_payload(attested)
    payload["attestation_digest"] = attestation_digest(payload)
    payload["status"] = "planned"
    return payload


def _load_run(run_id: object) -> LegacyMigrationRun:
    try:
        return LegacyMigrationRun.objects.select_related("organization").get(pk=run_id)
    except Exception:
        raise LegacyRehearsalResumeError("legacy_rehearsal_resume_run_not_found") from None


def _assert_resume_scope(run: LegacyMigrationRun, *, organization, attested: PhaseAAttestation) -> None:
    recorded = (
        run.organization_id,
        run.source_system,
        run.snapshot_sha256,
        run.transform_version,
        run.schema_version,
        run.mode,
        run.accounting_mode,
        run.source_row_count,
    )
    expected = (
        organization.pk,
        SOURCE_SYSTEM,
        attested.snapshot_sha256,
        attested.transform_version(),
        attested.schema_version,
        RUN_MODE,
        ACCOUNTING_MODE,
        attested.source_row_count,
    )
    if recorded != expected:
        raise LegacyRehearsalResumeError("legacy_rehearsal_resume_scope_mismatch")


def _resolve_run(*, attested, organization, actor, authorize, resume_run_id) -> LegacyMigrationRun:
    """B0-B2: resume an interrupted RUNNING run, or seal and start a new one."""

    if resume_run_id is not None:
        run = _load_run(resume_run_id)
        if run.status != LegacyMigrationRun.Status.RUNNING:
            raise LegacyRehearsalResumeError("legacy_rehearsal_resume_scope_mismatch")
        _assert_resume_scope(run, organization=organization, attested=attested)
        return run
    if LegacyMigrationRun.objects.filter(
        organization=organization,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=attested.snapshot_sha256,
        transform_version=attested.transform_version(),
        status=LegacyMigrationRun.Status.RUNNING,
    ).exists():
        raise LegacyRehearsalConfigError("legacy_rehearsal_scope_already_running")
    run = create_run(
        actor=actor,
        authorize=authorize,
        organization=organization,
        source_system=SOURCE_SYSTEM,
        snapshot_sha256=attested.snapshot_sha256,
        snapshot_size_bytes=attested.snapshot_size_bytes,
        source_row_count=attested.source_row_count,
        schema_version=attested.schema_version,
        transform_version=attested.transform_version(),
        mode=RUN_MODE,
        accounting_mode=ACCOUNTING_MODE,
        origin=LegacyMigrationRun.Origin.COMMAND,
    )
    return start_run(run_id=run.pk, actor=actor, authorize=authorize)


def _assert_apply_confirmation(apply_confirmation: object) -> None:
    """The operator must retype the disposable target database name verbatim."""

    settings_dict = getattr(default_connection, "settings_dict", None)
    expected = settings_dict.get("NAME") if isinstance(settings_dict, Mapping) else None
    if type(apply_confirmation) is not str or type(expected) is not str or apply_confirmation != expected:
        raise LegacyRehearsalConfigError("legacy_rehearsal_apply_confirmation_invalid")


def _finish_failed(run: LegacyMigrationRun, *, actor, authorize, failure_code: str) -> None:
    try:
        finish_run(
            run_id=run.pk,
            actor=actor,
            authorize=authorize,
            outcome=LegacyMigrationRun.Status.FAILED,
            failure_code=failure_code,
        )
    except Exception:
        # The original evidence failure is the reportable one; a refused
        # terminal transition must never mask it.
        return


def _drive_phases(
    *,
    run: LegacyMigrationRun,
    attested: PhaseAAttestation,
    organization,
    actor,
    authorize,
    email_trust_manifest_digests,
    cancellation_requested,
    stdout_note,
    snapshot,
) -> tuple[PhaseReport, ...]:
    """B5: drive the registry in its fixed order over the PRE-RUN (rebased) baseline."""

    email_policy = build_email_trust_policy(attested.policy, email_trust_manifest_digests)
    target_validators = build_target_validators()
    reports: list[PhaseReport] = []
    for phase in attested.phases:
        report = phase.run(
            RehearsalContext(
                run_id=run.pk,
                organization=organization,
                actor=actor,
                authorize=authorize,
                target_validators=target_validators,
                policy=attested.policy,
                plan=attested.plan,
                source_connection_factory=attested.source_factory,
                target_identity_snapshot=snapshot,
                authoritative_email_policy=email_policy,
                cancellation_requested=cancellation_requested,
                stdout_note=stdout_note,
            )
        )
        if report.observed_source_rows != phase.declared_source_rows(attested.plan):
            raise LegacyRehearsalEvidenceError("legacy_rehearsal_phase_row_count_mismatch")
        reports.append(normalized_phase_report(report))
    return tuple(reports)


def _stdout_payload(
    *,
    run: LegacyMigrationRun,
    attested: PhaseAAttestation,
    totals: Mapping[str, object],
    determinism_digest: str,
    status: str,
    failure_code: str,
    ordinal: int,
    report_path: str,
) -> dict[str, object]:
    return {
        "accounting_mode": ACCOUNTING_MODE,
        "determinism_digest": determinism_digest,
        "failure_code": failure_code,
        "mode": RUN_MODE,
        "phase_keys": [phase.phase_key for phase in attested.phases],
        "rehearsal_ordinal": ordinal,
        # The basename only: the artifact directory is a local path.
        "report_name": os.path.basename(report_path),
        "run_id": str(run.pk),
        "schema_version": attested.schema_version,
        "snapshot_sha256": attested.snapshot_sha256,
        "status": status,
        "totals": dict(totals),
        "transform_version": attested.transform_version(),
    }


def _publish(
    *,
    run: LegacyMigrationRun,
    attested: PhaseAAttestation,
    phase_reports: tuple[PhaseReport, ...],
    report_dir: str,
    ordinal: int,
    compare_report_path: str,
    actor: object = None,
    authorize: Callable | None = None,
    status: str = "",
    failure_code: str = "",
    baseline=None,
) -> RehearsalOutcome:
    """C5-C9: histogram, determinism digest, terminal transition, artifact."""

    histogram, blocking = issue_evidence(run)
    determinism = build_determinism_payload(
        plan=attested.plan,
        phase_registry_fingerprint=attested.phase_registry_fingerprint,
        snapshot_sha256=attested.snapshot_sha256,
        snapshot_size_bytes=attested.snapshot_size_bytes,
        schema_version=attested.schema_version,
        mode=RUN_MODE,
        accounting_mode=ACCOUNTING_MODE,
        policy=attested.policy,
        source_attestation=attested.source_attestation,
        target_guard=attested.guard.to_safe_log_dict(),
        target_identity_snapshot=baseline if baseline is not None else attested.baseline,
        phase_reports=phase_reports,
        issue_histogram=histogram,
        blocking_issue_count=blocking,
        credential_field_output_count=attested.credential_field_output_count,
        raw_pii_field_output_count=RAW_PII_FIELD_OUTPUT_COUNT,
    )
    determinism_digest = canonical_json_digest(determinism)
    mismatch = bool(compare_report_path) and read_report_determinism_digest(compare_report_path) != determinism_digest

    if authorize is not None:
        if blocking or mismatch:
            status = str(LegacyMigrationRun.Status.FAILED)
            failure_code = DETERMINISM_MISMATCH_CODE if mismatch else BLOCKING_ISSUE_FAILURE_CODE
        else:
            status = str(LegacyMigrationRun.Status.SUCCEEDED)
            failure_code = ""
        run = finish_run(
            run_id=run.pk,
            actor=actor,
            authorize=authorize,
            outcome=status,
            failure_code=failure_code,
        )
    report_path = write_report(
        report_dir=report_dir,
        ordinal=ordinal,
        payload=build_report_payload(
            determinism=determinism,
            provenance=provenance_payload(run, ordinal=ordinal, status=status),
        ),
    )
    return RehearsalOutcome(
        run_id=run.pk,
        status=status,
        failure_code=failure_code,
        determinism_digest=determinism_digest,
        report_path=report_path,
        payload=_stdout_payload(
            run=run,
            attested=attested,
            totals=determinism["totals"],
            determinism_digest=determinism_digest,
            status=status,
            failure_code=failure_code,
            ordinal=ordinal,
            report_path=report_path,
        ),
    )


def execute_rehearsal(
    *,
    settings_object: object,
    policy: RehearsalPolicy,
    organization: object,
    actor: object,
    report_dir: str,
    rehearsal_ordinal: int,
    apply_confirmation: object,
    source_path: str,
    source_size_bytes: int,
    resume_run_id: object = None,
    compare_report_path: str = "",
    emit_report_only: bool = False,
    email_trust_manifest_digests: frozenset[str] = frozenset(),
    cancellation_requested: Callable[[], bool] | None = None,
    stdout_note: Callable[[str], None] | None = None,
    source_preflight: Callable[..., Any] = inspect_legacy_source,
    source_factory_builder: Callable[[object], Any] = default_source_factory,
) -> RehearsalOutcome:
    """Drive one complete rehearsal attempt against a disposable target."""

    _assert_apply_confirmation(apply_confirmation)
    _assert_actor(actor)
    if emit_report_only and resume_run_id is None:
        raise LegacyRehearsalConfigError("legacy_rehearsal_report_run_required")
    authorize = build_rehearsal_authorizer()
    attested = attest_phase_a(
        settings_object=settings_object,
        policy=policy,
        organization=organization,
        source_path=source_path,
        source_size_bytes=source_size_bytes,
        source_preflight=source_preflight,
        source_factory_builder=source_factory_builder,
        enforce_scope_precheck=not emit_report_only,
    )
    if emit_report_only:
        run = _load_run(resume_run_id)
        _assert_resume_scope(run, organization=organization, attested=attested)
        return _publish(
            run=run,
            attested=attested,
            phase_reports=tuple(
                phase_report_from_ledger(run, phase=phase, plan=attested.plan) for phase in attested.phases
            ),
            report_dir=report_dir,
            ordinal=rehearsal_ordinal,
            compare_report_path=compare_report_path,
            status=run.status,
            failure_code=run.failure_code,
            baseline=rebase_target_snapshot_for_run(attested.baseline, run_id=run.pk),
        )

    run = _resolve_run(
        attested=attested,
        organization=organization,
        actor=actor,
        authorize=authorize,
        resume_run_id=resume_run_id,
    )
    # B4 rebase B3 anchor-dan ƏVVƏL: resume-da anchor digest-i dəyişməməlidir
    # (2026-08-26: legacy_issue_identity_conflict — inteqrasiya testinin tapıntısı).
    rebased_baseline = rebase_target_snapshot_for_run(attested.baseline, run_id=run.pk)
    upsert_issue(
        run_id=run.pk,
        actor=actor,
        authorize=authorize,
        source_table=ATTESTATION_SOURCE_TABLE,
        entity_type=ATTESTATION_ENTITY_TYPE,
        legacy_pk=ATTESTATION_LEGACY_PK,
        rule_code=ATTESTATION_RULE_CODE,
        severity=ISSUE_SEVERITY[ATTESTATION_RULE_CODE],
        payload_digest=attestation_digest(attestation_payload(attested, baseline=rebased_baseline)),
        entity_map_id=None,
    )
    try:
        phase_reports = _drive_phases(
            run=run,
            attested=attested,
            organization=organization,
            actor=actor,
            authorize=authorize,
            email_trust_manifest_digests=email_trust_manifest_digests,
            cancellation_requested=cancellation_requested or (lambda: False),
            stdout_note=stdout_note or (lambda _note: None),
            snapshot=rebased_baseline,
        )
        reconcile_run(run, phases=attested.phases, plan=attested.plan)
    except LegacyRehearsalEvidenceError as exc:
        _finish_failed(run, actor=actor, authorize=authorize, failure_code=exc.code)
        raise
    return _publish(
        run=run,
        attested=attested,
        phase_reports=phase_reports,
        report_dir=report_dir,
        ordinal=rehearsal_ordinal,
        compare_report_path=compare_report_path,
        actor=actor,
        authorize=authorize,
        baseline=rebased_baseline,
    )


def cancel_rehearsal(
    *,
    settings_object: object,
    organization: object,
    actor: object,
    run_id: object,
) -> RehearsalOutcome:
    """Finish an interrupted RUNNING run as CANCELLED without opening a source."""

    assert_disposable_rehearsal_target(settings_object=settings_object)
    if organization is None or getattr(organization, "pk", None) is None:
        raise LegacyRehearsalConfigError("legacy_rehearsal_organization_invalid")
    _assert_actor(actor)
    set_rls_tenant(organization.pk, local=False)
    run = _load_run(run_id)
    if run.organization_id != organization.pk:
        raise LegacyRehearsalResumeError("legacy_rehearsal_resume_scope_mismatch")
    run = finish_run(
        run_id=run.pk,
        actor=actor,
        authorize=build_rehearsal_authorizer(),
        outcome=LegacyMigrationRun.Status.CANCELLED,
        failure_code=CANCELLED_FAILURE_CODE,
    )
    return RehearsalOutcome(
        run_id=run.pk,
        status=run.status,
        failure_code=run.failure_code,
        determinism_digest="",
        report_path="",
        payload={"failure_code": run.failure_code, "run_id": str(run.pk), "status": run.status},
    )


__all__ = [
    "RehearsalOutcome",
    "cancel_rehearsal",
    "execute_rehearsal",
    "plan_rehearsal",
]
