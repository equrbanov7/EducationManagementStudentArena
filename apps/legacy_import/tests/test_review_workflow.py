from django.db.models.deletion import ProtectedError
from django.db.models.signals import post_save

import pytest

from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityMapVersion,
    LegacyEntityObservation,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.services.ledger import (
    LegacyLedgerAuthorizationError,
    LegacyLedgerConflictError,
    LegacyLedgerTargetError,
    LegacyLedgerTransitionError,
    TargetValidation,
    create_run,
    finish_run,
    start_run,
    upsert_entity_map,
    upsert_issue,
)
from apps.legacy_import.services.review import review_and_remap_entity, review_issue
from apps.organizations.models import Organization
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _allow(**_kwargs):
    return True


def _target_ok(**_kwargs):
    return TargetValidation(exists=True, organization_matches=True)


@pytest.fixture()
def organization_actor(db, django_user_model):
    actor = django_user_model.objects.create_user(
        username="legacy_review_owner",
        email="legacy-review-owner@example.test",
        password="test-only",
    )
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        organization = Organization.objects.create(
            name="Legacy Review Organization",
            slug="legacy-review-organization",
            org_type=OrganizationType.UNIVERSITY,
            owner=actor,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return organization, actor


def _run(organization, actor, *, transform_version="transform-v1"):
    run = create_run(
        actor=actor,
        authorize=_allow,
        organization=organization,
        source_system="myedu_mariadb",
        snapshot_sha256=SHA_A,
        snapshot_size_bytes=100,
        source_row_count=1,
        schema_version="legacy-v1",
        transform_version=transform_version,
        mode=LegacyMigrationRun.Mode.REHEARSAL,
    )
    return start_run(run_id=run.pk, actor=actor, authorize=_allow)


def _map(run, actor, *, target_pk="42"):
    return upsert_entity_map(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        entity_type="student",
        legacy_pk="1001",
        source_row_hash=SHA_B,
        state=LegacyEntityMap.State.MIGRATED,
        target_model_label="accounts.profile",
        target_pk=target_pk,
        target_validators={"accounts.profile": _target_ok},
    )


def _conflict_issue(run, actor, entity_map):
    return upsert_issue(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        source_table="students",
        entity_type=entity_map.entity_type,
        legacy_pk=entity_map.legacy_pk,
        rule_code="legacy_entity_identity_conflict",
        severity=LegacyMigrationIssue.Severity.ERROR,
        payload_digest=SHA_C,
        entity_map_id=entity_map.pk,
    )


@pytest.mark.django_db
def test_issue_review_requires_authorization_and_persisted_actor(organization_actor):
    organization, actor = organization_actor
    run = _run(organization, actor)
    issue = upsert_issue(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        source_table="students",
        entity_type="student",
        legacy_pk="1001",
        rule_code="manual-review",
        severity=LegacyMigrationIssue.Severity.WARNING,
        payload_digest=SHA_A,
    )

    with pytest.raises(LegacyLedgerAuthorizationError) as denied:
        review_issue(
            issue_id=issue.pk,
            actor=actor,
            authorize=lambda **_kwargs: False,
            decision=LegacyMigrationIssue.ReviewStatus.RESOLVED,
            reason_code="validated-source",
            evidence_digest=SHA_B,
        )
    assert denied.value.code == "legacy_authorization_denied"
    with pytest.raises(LegacyLedgerAuthorizationError) as missing_actor:
        review_issue(
            issue_id=issue.pk,
            actor=object(),
            authorize=_allow,
            decision=LegacyMigrationIssue.ReviewStatus.RESOLVED,
            reason_code="validated-source",
            evidence_digest=SHA_B,
        )
    assert missing_actor.value.code == "legacy_review_actor_required"
    issue.refresh_from_db()
    assert issue.review_status == LegacyMigrationIssue.ReviewStatus.OPEN
    assert issue.reviewed_by_id is None


@pytest.mark.django_db
def test_review_records_sanitized_evidence_and_terminal_decision_is_idempotent(organization_actor):
    organization, actor = organization_actor
    run = _run(organization, actor)
    issue = upsert_issue(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        source_table="students",
        entity_type="student",
        legacy_pk="1001",
        rule_code="manual-review",
        severity=LegacyMigrationIssue.Severity.WARNING,
        payload_digest=SHA_A,
    )

    reviewed = review_issue(
        issue_id=issue.pk,
        actor=actor,
        authorize=_allow,
        decision=LegacyMigrationIssue.ReviewStatus.RESOLVED,
        reason_code="validated-source",
        evidence_digest=SHA_B,
    )
    repeated = review_issue(
        issue_id=issue.pk,
        actor=actor,
        authorize=_allow,
        decision=LegacyMigrationIssue.ReviewStatus.RESOLVED,
        reason_code="validated-source",
        evidence_digest=SHA_B,
    )

    assert reviewed.reviewed_by_id == actor.pk
    assert reviewed.reviewed_at is not None
    assert repeated.reviewed_at == reviewed.reviewed_at
    with pytest.raises(LegacyLedgerTransitionError) as terminal:
        review_issue(
            issue_id=issue.pk,
            actor=actor,
            authorize=_allow,
            decision=LegacyMigrationIssue.ReviewStatus.WAIVED,
            reason_code="different-decision",
            evidence_digest=SHA_C,
        )
    assert terminal.value.code == "legacy_review_terminal"


@pytest.mark.django_db
def test_same_review_decision_cannot_rewrite_evidence(organization_actor):
    organization, actor = organization_actor
    run = _run(organization, actor)
    issue = upsert_issue(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        source_table="students",
        entity_type="student",
        legacy_pk="1001",
        rule_code="manual-review",
        severity=LegacyMigrationIssue.Severity.WARNING,
        payload_digest=SHA_A,
    )
    review_issue(
        issue_id=issue.pk,
        actor=actor,
        authorize=_allow,
        decision=LegacyMigrationIssue.ReviewStatus.ACKNOWLEDGED,
        reason_code="operator-ack",
        evidence_digest=SHA_B,
    )

    with pytest.raises(LegacyLedgerConflictError) as conflict:
        review_issue(
            issue_id=issue.pk,
            actor=actor,
            authorize=_allow,
            decision=LegacyMigrationIssue.ReviewStatus.ACKNOWLEDGED,
            reason_code="rewritten-evidence",
            evidence_digest=SHA_C,
        )
    assert conflict.value.code == "legacy_review_evidence_conflict"


@pytest.mark.django_db
def test_severity_reopen_keeps_last_review_evidence_until_new_decision(organization_actor):
    organization, actor = organization_actor
    run = _run(organization, actor)
    values = {
        "run_id": run.pk,
        "actor": actor,
        "authorize": _allow,
        "source_table": "students",
        "entity_type": "student",
        "legacy_pk": "1001",
        "rule_code": "manual-review",
        "payload_digest": SHA_A,
    }
    issue = upsert_issue(severity=LegacyMigrationIssue.Severity.WARNING, **values)
    reviewed = review_issue(
        issue_id=issue.pk,
        actor=actor,
        authorize=_allow,
        decision=LegacyMigrationIssue.ReviewStatus.RESOLVED,
        reason_code="first-review",
        evidence_digest=SHA_B,
    )

    reopened = upsert_issue(severity=LegacyMigrationIssue.Severity.ERROR, **values)

    assert reopened.review_status == LegacyMigrationIssue.ReviewStatus.OPEN
    assert reopened.reviewed_by_id == reviewed.reviewed_by_id
    assert reopened.reviewed_at == reviewed.reviewed_at
    assert reopened.review_evidence_digest == SHA_B
    second = review_issue(
        issue_id=issue.pk,
        actor=actor,
        authorize=_allow,
        decision=LegacyMigrationIssue.ReviewStatus.RESOLVED,
        reason_code="second-review",
        evidence_digest=SHA_C,
    )
    assert second.reviewed_at > reviewed.reviewed_at
    assert second.review_evidence_digest == SHA_C


@pytest.mark.django_db
def test_reviewed_remap_appends_lineage_without_overwriting_canonical_identity(organization_actor):
    organization, actor = organization_actor
    first_run = _run(organization, actor)
    entity_map = _map(first_run, actor, target_pk="42")
    first_observation = LegacyEntityObservation.objects.get(run=first_run, entity_map=entity_map)
    finish_run(
        run_id=first_run.pk,
        actor=actor,
        authorize=_allow,
        outcome=LegacyMigrationRun.Status.SUCCEEDED,
    )
    second_run = _run(organization, actor, transform_version="transform-v2")
    with pytest.raises(LegacyLedgerConflictError) as conflict:
        _map(second_run, actor, target_pk="43")
    assert conflict.value.code == "legacy_entity_identity_conflict"
    issue = _conflict_issue(second_run, actor, entity_map)
    review_issue(
        issue_id=issue.pk,
        actor=actor,
        authorize=_allow,
        decision=LegacyMigrationIssue.ReviewStatus.RESOLVED,
        reason_code="approved-remap",
        evidence_digest=SHA_A,
    )

    replacement = review_and_remap_entity(
        issue_id=issue.pk,
        actor=actor,
        authorize=_allow,
        source_row_hash=SHA_B,
        state=LegacyEntityMap.State.MIGRATED,
        target_model_label="accounts.profile",
        target_pk="43",
        target_validators={"accounts.profile": _target_ok},
    )

    entity_map.refresh_from_db()
    first_observation.refresh_from_db()
    assert entity_map.target_pk == "42"
    assert entity_map.transform_version == "transform-v1"
    assert first_observation.target_pk == "42"
    assert replacement.version_number == 2
    assert replacement.supersedes.version_number == 1
    assert replacement.target_pk == "43"
    assert replacement.reviewed_by_id == actor.pk
    assert replacement.applied_by_id == actor.pk
    second_observation = LegacyEntityObservation.objects.get(run=second_run, entity_map=entity_map)
    assert second_observation.map_version_id == replacement.pk
    assert second_observation.target_pk == "43"
    assert _map(second_run, actor, target_pk="43").pk == entity_map.pk
    assert LegacyEntityObservation.objects.filter(run=second_run, entity_map=entity_map).count() == 1
    assert LegacyEntityMapVersion.objects.filter(entity_map=entity_map).count() == 2
    finish_run(
        run_id=second_run.pk,
        actor=actor,
        authorize=_allow,
        outcome=LegacyMigrationRun.Status.SUCCEEDED,
    )


@pytest.mark.django_db
def test_remap_requires_resolved_conflict_and_same_tenant_target(organization_actor):
    organization, actor = organization_actor
    first_run = _run(organization, actor)
    entity_map = _map(first_run, actor)
    finish_run(
        run_id=first_run.pk,
        actor=actor,
        authorize=_allow,
        outcome=LegacyMigrationRun.Status.SUCCEEDED,
    )
    second_run = _run(organization, actor, transform_version="transform-v2")
    issue = _conflict_issue(second_run, actor, entity_map)
    values = {
        "issue_id": issue.pk,
        "actor": actor,
        "authorize": _allow,
        "source_row_hash": SHA_B,
        "state": LegacyEntityMap.State.MIGRATED,
        "target_model_label": "accounts.profile",
        "target_pk": "43",
    }

    with pytest.raises(LegacyLedgerTransitionError) as no_review:
        review_and_remap_entity(
            **values,
            target_validators={"accounts.profile": _target_ok},
        )
    assert no_review.value.code == "legacy_remap_review_required"
    review_issue(
        issue_id=issue.pk,
        actor=actor,
        authorize=_allow,
        decision=LegacyMigrationIssue.ReviewStatus.RESOLVED,
        reason_code="approved-remap",
        evidence_digest=SHA_A,
    )
    with pytest.raises(LegacyLedgerTargetError) as cross_tenant:
        review_and_remap_entity(
            **values,
            target_validators={
                "accounts.profile": lambda **_kwargs: TargetValidation(
                    exists=True,
                    organization_matches=False,
                )
            },
        )
    assert cross_tenant.value.code == "legacy_target_cross_organization"
    assert LegacyEntityMapVersion.objects.filter(entity_map=entity_map).count() == 1
    assert not LegacyEntityObservation.objects.filter(run=second_run, entity_map=entity_map).exists()


@pytest.mark.django_db
def test_mapping_versions_are_non_deletable(organization_actor):
    organization, actor = organization_actor
    run = _run(organization, actor)
    entity_map = _map(run, actor)
    version = LegacyEntityMapVersion.objects.get(entity_map=entity_map, version_number=1)

    with pytest.raises(ProtectedError):
        version.delete()
    with pytest.raises(ProtectedError):
        LegacyEntityMapVersion.objects.filter(pk=version.pk).delete()
