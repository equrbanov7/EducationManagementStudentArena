"""Sanctioned issue review and append-only canonical remap workflow."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityMapVersion,
    LegacyEntityObservation,
    LegacyMigrationIssue,
)
from apps.legacy_import.services import ledger
from apps.legacy_import.services.versioning import SNAPSHOT_FIELDS, InitialVersionConflictError, latest_version


def _get_issue(issue_id: Any, *, for_update=False) -> LegacyMigrationIssue:
    queryset = LegacyMigrationIssue.objects.select_related("organization", "run")
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    try:
        return queryset.get(pk=issue_id)
    except (LegacyMigrationIssue.DoesNotExist, ValidationError, TypeError, ValueError):
        raise ledger.LegacyLedgerConflictError("legacy_issue_not_found") from None


def _issue_scope(issue_id: Any) -> tuple[str, str, str, str]:
    return ledger._scope_parts(_get_issue(issue_id).run)


def _persisted_actor(actor: Any) -> Any:
    user_model = LegacyMigrationIssue._meta.get_field("reviewed_by").remote_field.model
    if not isinstance(actor, user_model) or actor.pk is None:
        raise ledger.LegacyLedgerAuthorizationError("legacy_review_actor_required")
    if not user_model._default_manager.filter(pk=actor.pk).exists():
        raise ledger.LegacyLedgerAuthorizationError("legacy_review_actor_required")
    return actor


def _next_review_time(issue: LegacyMigrationIssue):
    reviewed_at = timezone.now()
    if issue.reviewed_at and reviewed_at <= issue.reviewed_at:
        reviewed_at = issue.reviewed_at + timedelta(microseconds=1)
    return reviewed_at


def review_issue(
    *,
    issue_id: Any,
    actor: Any,
    authorize: ledger.LedgerAuthorizer,
    decision: str,
    reason_code: str,
    evidence_digest: str,
) -> LegacyMigrationIssue:
    """Record an explicit review decision without accepting free-form context."""

    allowed = {
        LegacyMigrationIssue.ReviewStatus.ACKNOWLEDGED,
        LegacyMigrationIssue.ReviewStatus.RESOLVED,
        LegacyMigrationIssue.ReviewStatus.WAIVED,
    }
    if decision not in allowed:
        raise ledger.LegacyLedgerTransitionError("legacy_review_decision_invalid")
    scope = _issue_scope(issue_id)
    with ledger._locked_scope(scope):
        issue = _get_issue(issue_id, for_update=True)
        reviewer = _persisted_actor(actor)
        ledger._authorize(
            actor=reviewer,
            organization=issue.organization,
            action=ledger.LedgerAction.REVIEW_ISSUE,
            authorize=authorize,
        )
        same_decision = (
            issue.review_status == decision
            and issue.reviewed_by_id == reviewer.pk
            and issue.review_reason_code == reason_code
            and issue.review_evidence_digest == evidence_digest
        )
        if same_decision:
            return issue
        if issue.review_status == decision:
            raise ledger.LegacyLedgerConflictError("legacy_review_evidence_conflict")
        if issue.review_status in {
            LegacyMigrationIssue.ReviewStatus.RESOLVED,
            LegacyMigrationIssue.ReviewStatus.WAIVED,
        }:
            raise ledger.LegacyLedgerTransitionError("legacy_review_terminal")
        issue.review_status = decision
        issue.reviewed_by = reviewer
        issue.reviewed_at = _next_review_time(issue)
        issue.review_reason_code = reason_code
        issue.review_evidence_digest = evidence_digest
        ledger._validated_save(issue)
    return issue


def review_and_remap_entity(
    *,
    issue_id: Any,
    actor: Any,
    authorize: ledger.LedgerAuthorizer,
    source_row_hash: str,
    state: str,
    target_model_label: str = "",
    target_pk: str = "",
    reconciliation_status: str = LegacyEntityMap.ReconciliationStatus.PENDING,
    target_validators: ledger.TargetValidatorRegistry,
) -> LegacyEntityMapVersion:
    """Apply one already-resolved conflict review as a new canonical version."""

    scope = _issue_scope(issue_id)
    with ledger._locked_scope(scope):
        issue = _get_issue(issue_id, for_update=True)
        applier = _persisted_actor(actor)
        ledger._authorize(
            actor=applier,
            organization=issue.organization,
            action=ledger.LedgerAction.REMAP_ENTITY,
            authorize=authorize,
        )
        ledger._require_active_run(issue.run)
        if (
            issue.rule_code != "legacy_entity_identity_conflict"
            or issue.review_status != LegacyMigrationIssue.ReviewStatus.RESOLVED
            or issue.entity_map_id is None
            or issue.reviewed_by_id is None
            or issue.reviewed_at is None
            or not issue.review_reason_code
            or not issue.review_evidence_digest
        ):
            raise ledger.LegacyLedgerTransitionError("legacy_remap_review_required")
        entity_map = LegacyEntityMap.objects.select_for_update().get(pk=issue.entity_map_id)
        if (
            entity_map.organization_id != issue.organization_id
            or entity_map.source_system != issue.run.source_system
            or entity_map.entity_type != issue.entity_type
            or entity_map.legacy_pk != issue.legacy_pk
        ):
            raise ledger.LegacyLedgerConflictError("legacy_remap_scope_mismatch")
        if LegacyEntityObservation.objects.filter(run=issue.run, entity_map=entity_map).exists():
            raise ledger.LegacyLedgerConflictError("legacy_remap_run_already_observed")
        if state == LegacyEntityMap.State.MIGRATED:
            ledger._target_validation(
                target_model_label=target_model_label,
                target_pk=target_pk,
                organization=issue.organization,
                target_validators=target_validators,
            )
        values = {
            "source_row_hash": source_row_hash,
            "transform_version": issue.run.transform_version,
            "target_model_label": target_model_label,
            "target_pk": target_pk,
            "state": state,
            "reconciliation_status": reconciliation_status,
        }
        try:
            predecessor = latest_version(entity_map, for_update=True)
        except InitialVersionConflictError:
            raise ledger.LegacyLedgerConflictError("legacy_initial_version_conflict") from None
        if all(getattr(predecessor, field) == values[field] for field in SNAPSHOT_FIELDS):
            raise ledger.LegacyLedgerConflictError("legacy_remap_no_change")
        version = LegacyEntityMapVersion(
            organization=issue.organization,
            entity_map=entity_map,
            version_number=predecessor.version_number + 1,
            supersedes=predecessor,
            recorded_run=issue.run,
            approved_issue=issue,
            reviewed_by=issue.reviewed_by,
            reviewed_at=issue.reviewed_at,
            review_reason_code=issue.review_reason_code,
            review_evidence_digest=issue.review_evidence_digest,
            applied_by=applier,
            **values,
        )
        ledger._validated_save(version)
        observation = LegacyEntityObservation(
            organization=issue.organization,
            run=issue.run,
            entity_map=entity_map,
            map_version=version,
            **values,
        )
        ledger._validated_save(observation)
    return version
