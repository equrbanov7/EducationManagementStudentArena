"""Sanctioned writes for the PII-minimised legacy-import control-plane ledger.

Raw payloads and credentials are never accepted, but opaque legacy identifiers
and stable digests remain linkable pseudonymous data.  This module deliberately
knows nothing about domain models.  A caller that wants to record a migrated
target must supply an explicit model-label allowlist whose validator proves
both target existence and tenant ownership.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils import timezone

from apps.legacy_import.models import LegacyEntityMap, LegacyEntityObservation, LegacyMigrationIssue, LegacyMigrationRun
from apps.legacy_import.services.ledger_locks import (  # noqa: F401 - advisory_lock_key compatibility export
    LedgerScopeBusyError,
    advisory_lock_key,
    locked_scope,
)
from apps.legacy_import.services.versioning import InitialVersionConflictError, latest_version


class LedgerAction(str, Enum):
    CREATE_RUN = "legacy_import.create_run"
    START_RUN = "legacy_import.start_run"
    FINISH_RUN = "legacy_import.finish_run"
    RECORD_BATCH = "legacy_import.record_batch"
    UPSERT_MAP = "legacy_import.upsert_map"
    UPSERT_ISSUE = "legacy_import.upsert_issue"
    REVIEW_ISSUE = "legacy_import.review_issue"
    REMAP_ENTITY = "legacy_import.remap_entity"


class LedgerAuthorizer(Protocol):
    """Dependency-injected bridge to the platform's centralized policy."""

    def __call__(self, *, actor: Any, organization: Any, action: LedgerAction) -> bool: ...


@dataclass(frozen=True)
class TargetValidation:
    """Required result from a domain-owned target validator."""

    exists: bool
    organization_matches: bool


class TargetValidator(Protocol):
    def __call__(self, *, target_pk: str, organization: Any) -> TargetValidation: ...


TargetValidatorRegistry = Mapping[str, TargetValidator]


class LegacyLedgerError(Exception):
    """Sanitized service error identified only by a stable machine code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class LegacyLedgerAuthorizationError(LegacyLedgerError):
    pass


class LegacyLedgerBusyError(LegacyLedgerError):
    pass


class LegacyLedgerTransitionError(LegacyLedgerError):
    pass


class LegacyLedgerTargetError(LegacyLedgerError):
    pass


class LegacyLedgerConflictError(LegacyLedgerError):
    pass


def _authorize(
    *,
    actor: Any,
    organization: Any,
    action: LedgerAction,
    authorize: LedgerAuthorizer,
) -> None:
    if not callable(authorize):
        raise LegacyLedgerAuthorizationError("legacy_authorizer_required")
    try:
        authorized = authorize(actor=actor, organization=organization, action=action)
    except Exception:
        raise LegacyLedgerAuthorizationError("legacy_authorization_failed") from None
    if authorized is not True:
        raise LegacyLedgerAuthorizationError("legacy_authorization_denied")


def _scope_parts(run: LegacyMigrationRun) -> tuple[str, str, str, str]:
    return (
        str(run.organization_id),
        run.source_system,
        run.snapshot_sha256,
        run.transform_version,
    )


def _locked_scope(scope):
    """Translate the low-level lock signal to the ledger's public error."""

    class _ScopeContext:
        def __enter__(self):
            self._context = locked_scope(scope)
            try:
                return self._context.__enter__()
            except LedgerScopeBusyError:
                raise LegacyLedgerBusyError("legacy_scope_busy") from None

        def __exit__(self, exc_type, exc_value, traceback):
            return self._context.__exit__(exc_type, exc_value, traceback)

    return _ScopeContext()


def _validated_save(instance: Any) -> None:
    instance.full_clean(validate_constraints=True)
    instance.save()


def _get_run(run_id: Any, *, for_update: bool = False) -> LegacyMigrationRun:
    queryset = LegacyMigrationRun.objects.select_related("organization")
    if for_update:
        queryset = queryset.select_for_update()
    try:
        return queryset.get(pk=run_id)
    except (LegacyMigrationRun.DoesNotExist, ValidationError, TypeError, ValueError):
        raise LegacyLedgerConflictError("legacy_run_not_found") from None


def _get_run_scope(run_id: Any) -> tuple[str, str, str, str]:
    return _scope_parts(_get_run(run_id))


def _require_status(run: LegacyMigrationRun, expected: str) -> None:
    if run.status != expected:
        raise LegacyLedgerTransitionError("legacy_transition_invalid")


def _require_pristine_pending(run: LegacyMigrationRun) -> None:
    _require_status(run, LegacyMigrationRun.Status.PENDING)
    if (
        run.started_at is not None
        or run.finished_at is not None
        or run.migrated_count != 0
        or run.skipped_count != 0
        or run.quarantined_count != 0
        or run.failure_code
    ):
        raise LegacyLedgerTransitionError("legacy_pending_invariant_failed")


def _require_active_run(run: LegacyMigrationRun) -> None:
    _require_status(run, LegacyMigrationRun.Status.RUNNING)
    if (
        run.started_at is None
        or run.finished_at is not None
        or run.migrated_count != 0
        or run.skipped_count != 0
        or run.quarantined_count != 0
        or run.failure_code
    ):
        raise LegacyLedgerTransitionError("legacy_running_invariant_failed")


def _initiated_by(actor: Any) -> Any:
    user_model = LegacyMigrationRun._meta.get_field("initiated_by").remote_field.model
    if isinstance(actor, user_model) and actor.pk is not None:
        return actor
    return None


def create_run(
    *,
    actor: Any,
    authorize: LedgerAuthorizer,
    organization: Any,
    source_system: str,
    snapshot_sha256: str,
    snapshot_size_bytes: int,
    source_row_count: int,
    schema_version: str,
    transform_version: str,
    mode: str,
    accounting_mode: str = LegacyMigrationRun.AccountingMode.ROW,
    origin: str = LegacyMigrationRun.Origin.MANUAL,
) -> LegacyMigrationRun:
    """Create a pristine PENDING run without writing domain data."""

    run = LegacyMigrationRun(
        organization=organization,
        source_system=source_system,
        snapshot_sha256=snapshot_sha256,
        snapshot_size_bytes=snapshot_size_bytes,
        source_row_count=source_row_count,
        schema_version=schema_version,
        transform_version=transform_version,
        mode=mode,
        accounting_mode=accounting_mode,
        origin=origin,
        initiated_by=_initiated_by(actor),
        status=LegacyMigrationRun.Status.PENDING,
        started_at=None,
        finished_at=None,
        migrated_count=0,
        skipped_count=0,
        quarantined_count=0,
        failure_code="",
    )
    run.full_clean(validate_constraints=True)
    scope = _scope_parts(run)
    with _locked_scope(scope):
        _authorize(
            actor=actor,
            organization=organization,
            action=LedgerAction.CREATE_RUN,
            authorize=authorize,
        )
        _validated_save(run)
    return run


def start_run(
    *,
    run_id: Any,
    actor: Any,
    authorize: LedgerAuthorizer,
) -> LegacyMigrationRun:
    scope = _get_run_scope(run_id)
    with _locked_scope(scope):
        run = _get_run(run_id, for_update=True)
        _authorize(
            actor=actor,
            organization=run.organization,
            action=LedgerAction.START_RUN,
            authorize=authorize,
        )
        _require_pristine_pending(run)
        another_active = LegacyMigrationRun.objects.filter(
            organization_id=run.organization_id,
            source_system=run.source_system,
            snapshot_sha256=run.snapshot_sha256,
            transform_version=run.transform_version,
            status=LegacyMigrationRun.Status.RUNNING,
        ).exclude(pk=run.pk)
        if another_active.exists():
            raise LegacyLedgerBusyError("legacy_scope_already_running")
        run.status = LegacyMigrationRun.Status.RUNNING
        run.started_at = timezone.now()
        _validated_save(run)
    return run


def _target_validation(
    *,
    target_model_label: str,
    target_pk: str,
    organization: Any,
    target_validators: TargetValidatorRegistry,
) -> None:
    try:
        validator = target_validators.get(target_model_label)
    except AttributeError:
        raise LegacyLedgerTargetError("legacy_target_registry_invalid") from None
    if validator is None:
        raise LegacyLedgerTargetError("legacy_target_unregistered")
    try:
        result = validator(target_pk=target_pk, organization=organization)
    except Exception:
        raise LegacyLedgerTargetError("legacy_target_validation_failed") from None
    if (
        not isinstance(result, TargetValidation)
        or not isinstance(result.exists, bool)
        or not isinstance(result.organization_matches, bool)
    ):
        raise LegacyLedgerTargetError("legacy_target_validation_result_invalid")
    if not result.exists:
        raise LegacyLedgerTargetError("legacy_target_not_found")
    if not result.organization_matches:
        raise LegacyLedgerTargetError("legacy_target_cross_organization")


def upsert_entity_map(
    *,
    run_id: Any,
    actor: Any,
    authorize: LedgerAuthorizer,
    entity_type: str,
    legacy_pk: str,
    source_row_hash: str,
    state: str,
    target_model_label: str = "",
    target_pk: str = "",
    reconciliation_status: str = LegacyEntityMap.ReconciliationStatus.PENDING,
    target_validators: TargetValidatorRegistry,
) -> LegacyEntityMap:
    """Create one canonical mapping and an immutable per-run observation."""

    scope = _get_run_scope(run_id)
    with _locked_scope(scope):
        run = _get_run(run_id, for_update=True)
        _authorize(
            actor=actor,
            organization=run.organization,
            action=LedgerAction.UPSERT_MAP,
            authorize=authorize,
        )
        _require_active_run(run)
        if state == LegacyEntityMap.State.MIGRATED:
            _target_validation(
                target_model_label=target_model_label,
                target_pk=target_pk,
                organization=run.organization,
                target_validators=target_validators,
            )
        canonical_values = {
            "source_row_hash": source_row_hash,
            "transform_version": run.transform_version,
            "target_model_label": target_model_label,
            "target_pk": target_pk,
            "state": state,
            "reconciliation_status": reconciliation_status,
        }
        entity_map = (
            LegacyEntityMap.objects.select_for_update()
            .filter(
                organization_id=run.organization_id,
                source_system=run.source_system,
                entity_type=entity_type,
                legacy_pk=legacy_pk,
            )
            .first()
        )
        if entity_map is None:
            entity_map = LegacyEntityMap(
                organization=run.organization,
                source_system=run.source_system,
                entity_type=entity_type,
                legacy_pk=legacy_pk,
                created_run=run,
                **canonical_values,
            )
            _validated_save(entity_map)
        try:
            current_version = latest_version(entity_map, for_update=True)
        except InitialVersionConflictError:
            raise LegacyLedgerConflictError("legacy_initial_version_conflict") from None
        if any(getattr(current_version, field) != value for field, value in canonical_values.items()):
            raise LegacyLedgerConflictError("legacy_entity_identity_conflict")
        observation = LegacyEntityObservation.objects.select_for_update().filter(run=run, entity_map=entity_map).first()
        if observation is None:
            observation = LegacyEntityObservation(
                organization=run.organization,
                run=run,
                entity_map=entity_map,
                map_version=current_version,
                **canonical_values,
            )
            _validated_save(observation)
        elif observation.map_version_id != current_version.pk or any(
            getattr(observation, field) != value for field, value in canonical_values.items()
        ):
            raise LegacyLedgerConflictError("legacy_entity_observation_conflict")
    return entity_map


def _get_issue_map(
    *,
    entity_map_id: Any,
    run: LegacyMigrationRun,
    entity_type: str,
    legacy_pk: str,
    rule_code: str,
) -> LegacyEntityMap | None:
    if entity_map_id is None:
        return None
    try:
        entity_map = LegacyEntityMap.objects.select_for_update().get(pk=entity_map_id)
    except (LegacyEntityMap.DoesNotExist, ValidationError, TypeError, ValueError):
        raise LegacyLedgerConflictError("legacy_issue_map_not_found") from None
    if (
        entity_map.organization_id != run.organization_id
        or entity_map.source_system != run.source_system
        or entity_map.entity_type != entity_type
        or entity_map.legacy_pk != legacy_pk
    ):
        raise LegacyLedgerConflictError("legacy_issue_map_scope_mismatch")
    if (
        rule_code != "legacy_entity_identity_conflict"
        and not LegacyEntityObservation.objects.filter(
            run=run,
            entity_map=entity_map,
            transform_version=run.transform_version,
        ).exists()
    ):
        raise LegacyLedgerConflictError("legacy_issue_map_scope_mismatch")
    return entity_map


_SEVERITY_RANK = {
    LegacyMigrationIssue.Severity.INFO: 0,
    LegacyMigrationIssue.Severity.WARNING: 1,
    LegacyMigrationIssue.Severity.ERROR: 2,
    LegacyMigrationIssue.Severity.CRITICAL: 3,
}


def upsert_issue(
    *,
    run_id: Any,
    actor: Any,
    authorize: LedgerAuthorizer,
    source_table: str,
    entity_type: str,
    legacy_pk: str,
    rule_code: str,
    severity: str,
    payload_digest: str,
    entity_map_id: Any = None,
) -> LegacyMigrationIssue:
    """Record a sanitized, idempotent issue; raw context is not accepted."""

    scope = _get_run_scope(run_id)
    with _locked_scope(scope):
        run = _get_run(run_id, for_update=True)
        _authorize(
            actor=actor,
            organization=run.organization,
            action=LedgerAction.UPSERT_ISSUE,
            authorize=authorize,
        )
        _require_active_run(run)
        entity_map = _get_issue_map(
            entity_map_id=entity_map_id,
            run=run,
            entity_type=entity_type,
            legacy_pk=legacy_pk,
            rule_code=rule_code,
        )
        issue = (
            LegacyMigrationIssue.objects.select_for_update()
            .filter(
                run=run,
                source_table=source_table,
                legacy_pk=legacy_pk,
                rule_code=rule_code,
            )
            .first()
        )
        if issue is None:
            issue = LegacyMigrationIssue(
                organization=run.organization,
                run=run,
                source_table=source_table,
                entity_type=entity_type,
                legacy_pk=legacy_pk,
                rule_code=rule_code,
                payload_digest=payload_digest,
                severity=severity,
                review_status=LegacyMigrationIssue.ReviewStatus.OPEN,
                entity_map=entity_map,
            )
        else:
            if issue.entity_type != entity_type or issue.payload_digest != payload_digest:
                raise LegacyLedgerConflictError("legacy_issue_identity_conflict")
            if issue.entity_map_id and entity_map_id and issue.entity_map_id != entity_map_id:
                raise LegacyLedgerConflictError("legacy_issue_map_conflict")
            if issue.entity_map_id is None and entity_map is not None:
                issue.entity_map = entity_map
            current_rank = _SEVERITY_RANK.get(issue.severity)
            incoming_rank = _SEVERITY_RANK.get(severity)
            if current_rank is None or incoming_rank is None:
                raise LegacyLedgerConflictError("legacy_issue_severity_invalid")
            if incoming_rank > current_rank:
                issue.severity = severity
                issue.review_status = LegacyMigrationIssue.ReviewStatus.OPEN
        _validated_save(issue)
    return issue


def _classified_counts(run: LegacyMigrationRun) -> dict[str, int]:
    from apps.legacy_import.services.batch_accounting import (
        classified_batch_counts,
        verify_batch_chains,
    )

    batch_counts = classified_batch_counts(run)
    if run.accounting_mode == LegacyMigrationRun.AccountingMode.BATCH:
        if batch_counts is None:
            return {
                LegacyEntityMap.State.MIGRATED: 0,
                LegacyEntityMap.State.SKIPPED: 0,
                LegacyEntityMap.State.QUARANTINED: 0,
            }
        verify_batch_chains(run)
        return {
            LegacyEntityMap.State.MIGRATED: batch_counts.migrated,
            LegacyEntityMap.State.SKIPPED: batch_counts.skipped,
            LegacyEntityMap.State.QUARANTINED: batch_counts.quarantined,
        }
    if batch_counts is not None:
        raise LegacyLedgerTransitionError("legacy_row_run_has_batch_evidence")
    counts = {
        LegacyEntityMap.State.MIGRATED: 0,
        LegacyEntityMap.State.SKIPPED: 0,
        LegacyEntityMap.State.QUARANTINED: 0,
    }
    rows = LegacyEntityObservation.objects.filter(run=run).values("state").annotate(total=Count("id"))
    for row in rows:
        if row["state"] not in counts:
            raise LegacyLedgerTransitionError("legacy_map_state_invalid")
        counts[row["state"]] = row["total"]
    return counts


def finish_run(
    *,
    run_id: Any,
    actor: Any,
    authorize: LedgerAuthorizer,
    outcome: str,
    failure_code: str = "",
) -> LegacyMigrationRun:
    """Finish a RUNNING run using counts derived from its entity maps."""

    allowed_outcomes = {
        LegacyMigrationRun.Status.SUCCEEDED,
        LegacyMigrationRun.Status.FAILED,
        LegacyMigrationRun.Status.CANCELLED,
    }
    if outcome not in allowed_outcomes:
        raise LegacyLedgerTransitionError("legacy_terminal_status_invalid")
    scope = _get_run_scope(run_id)
    with _locked_scope(scope):
        run = _get_run(run_id, for_update=True)
        _authorize(
            actor=actor,
            organization=run.organization,
            action=LedgerAction.FINISH_RUN,
            authorize=authorize,
        )
        _require_active_run(run)
        counts = _classified_counts(run)
        classified_total = sum(counts.values())
        if classified_total > run.source_row_count:
            raise LegacyLedgerTransitionError("legacy_classified_count_exceeds_source")
        if outcome == LegacyMigrationRun.Status.SUCCEEDED:
            if failure_code:
                raise LegacyLedgerTransitionError("legacy_success_failure_code_forbidden")
            if classified_total != run.source_row_count:
                raise LegacyLedgerTransitionError("legacy_success_count_mismatch")
            unresolved_blocker = run.issues.filter(
                severity__in=[
                    LegacyMigrationIssue.Severity.ERROR,
                    LegacyMigrationIssue.Severity.CRITICAL,
                ]
            ).exclude(
                review_status__in=[
                    LegacyMigrationIssue.ReviewStatus.RESOLVED,
                    LegacyMigrationIssue.ReviewStatus.WAIVED,
                ]
            )
            if unresolved_blocker.exists():
                raise LegacyLedgerTransitionError("legacy_success_has_blocking_issue")
        elif not failure_code:
            raise LegacyLedgerTransitionError("legacy_terminal_failure_code_required")

        run.status = outcome
        run.finished_at = timezone.now()
        if run.finished_at < run.started_at:
            raise LegacyLedgerTransitionError("legacy_finished_before_started")
        run.migrated_count = counts[LegacyEntityMap.State.MIGRATED]
        run.skipped_count = counts[LegacyEntityMap.State.SKIPPED]
        run.quarantined_count = counts[LegacyEntityMap.State.QUARANTINED]
        run.failure_code = failure_code
        _validated_save(run)
    return run
