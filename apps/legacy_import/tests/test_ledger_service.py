import inspect

from django.db import connection
from django.db.models.signals import post_save

import pytest

from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityObservation,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.services import ledger, ledger_locks
from apps.legacy_import.services.ledger import (
    LegacyLedgerAuthorizationError,
    LegacyLedgerBusyError,
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
from apps.legacy_import.services.review import review_issue
from apps.organizations.models import Organization
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType

SHA_A = "a" * 64
SHA_B = "b" * 64


def _allow(**_kwargs):
    return True


def _make_organization(django_user_model, code):
    owner = django_user_model.objects.create_user(
        username=f"ledger_{code}_owner",
        email=f"ledger-{code}@example.test",
        password="test-only",
    )
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        organization = Organization.objects.create(
            name=f"Ledger {code.title()} Organization",
            slug=f"ledger-{code}-organization",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return organization, owner


@pytest.fixture()
def organization_actor(db, django_user_model):
    return _make_organization(django_user_model, "primary")


@pytest.fixture()
def other_organization_actor(db, django_user_model):
    return _make_organization(django_user_model, "other")


def _create_run(organization, actor, *, source_row_count=1, **overrides):
    values = {
        "actor": actor,
        "authorize": _allow,
        "organization": organization,
        "source_system": "myedu_mariadb",
        "snapshot_sha256": SHA_A,
        "snapshot_size_bytes": 100,
        "source_row_count": source_row_count,
        "schema_version": "legacy-v1",
        "transform_version": "transform-v1",
        "mode": LegacyMigrationRun.Mode.REHEARSAL,
    }
    values.update(overrides)
    return create_run(**values)


def _valid_target(**_kwargs):
    return TargetValidation(exists=True, organization_matches=True)


def _migrate_one(run, actor, *, legacy_pk="1001", target_pk="42"):
    return upsert_entity_map(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        entity_type="student",
        legacy_pk=legacy_pk,
        source_row_hash=SHA_B,
        state=LegacyEntityMap.State.MIGRATED,
        target_model_label="accounts.profile",
        target_pk=target_pk,
        target_validators={"accounts.profile": _valid_target},
    )


@pytest.mark.django_db
def test_authorizer_is_mandatory_and_denial_writes_nothing(organization_actor):
    organization, actor = organization_actor

    with pytest.raises(LegacyLedgerAuthorizationError) as exc_info:
        _create_run(organization, actor, authorize=lambda **_kwargs: False)

    assert exc_info.value.code == "legacy_authorization_denied"
    assert LegacyMigrationRun.objects.count() == 0


@pytest.mark.django_db
def test_lifecycle_is_strict_and_records_timestamps(organization_actor):
    organization, actor = organization_actor
    run = _create_run(organization, actor)

    running = start_run(run_id=run.pk, actor=actor, authorize=_allow)

    assert running.status == LegacyMigrationRun.Status.RUNNING
    assert running.started_at is not None
    assert running.finished_at is None
    with pytest.raises(LegacyLedgerTransitionError) as exc_info:
        start_run(run_id=run.pk, actor=actor, authorize=_allow)
    assert exc_info.value.code == "legacy_transition_invalid"


@pytest.mark.django_db
def test_second_run_for_same_scope_cannot_start(organization_actor):
    organization, actor = organization_actor
    first = _create_run(organization, actor)
    second = _create_run(organization, actor)
    start_run(run_id=first.pk, actor=actor, authorize=_allow)

    with pytest.raises(LegacyLedgerBusyError) as exc_info:
        start_run(run_id=second.pk, actor=actor, authorize=_allow)

    assert exc_info.value.code == "legacy_scope_already_running"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("registry", "code"),
    [
        ({}, "legacy_target_unregistered"),
        (
            {
                "accounts.profile": lambda **_kwargs: TargetValidation(
                    exists=False,
                    organization_matches=True,
                )
            },
            "legacy_target_not_found",
        ),
        (
            {
                "accounts.profile": lambda **_kwargs: TargetValidation(
                    exists=True,
                    organization_matches=False,
                )
            },
            "legacy_target_cross_organization",
        ),
    ],
)
def test_migrated_map_requires_allowlisted_existing_same_tenant_target(
    organization_actor,
    registry,
    code,
):
    organization, actor = organization_actor
    run = _create_run(organization, actor)
    start_run(run_id=run.pk, actor=actor, authorize=_allow)

    with pytest.raises(LegacyLedgerTargetError) as exc_info:
        upsert_entity_map(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            entity_type="student",
            legacy_pk="1001",
            source_row_hash=SHA_B,
            state=LegacyEntityMap.State.MIGRATED,
            target_model_label="accounts.profile",
            target_pk="42",
            target_validators=registry,
        )

    assert exc_info.value.code == code
    assert LegacyEntityMap.objects.count() == 0


@pytest.mark.django_db
def test_non_migrated_map_has_no_target_and_needs_no_adapter(organization_actor):
    organization, actor = organization_actor
    run = _create_run(organization, actor)
    start_run(run_id=run.pk, actor=actor, authorize=_allow)

    entity_map = upsert_entity_map(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        entity_type="student",
        legacy_pk="1001",
        source_row_hash=SHA_B,
        state=LegacyEntityMap.State.QUARANTINED,
        reconciliation_status=LegacyEntityMap.ReconciliationStatus.NOT_APPLICABLE,
        target_validators={},
    )

    assert entity_map.target_model_label == ""
    assert entity_map.target_pk == ""


@pytest.mark.django_db
def test_map_upsert_is_exact_noop_and_rejects_changed_target(organization_actor):
    organization, actor = organization_actor
    run = _create_run(organization, actor)
    start_run(run_id=run.pk, actor=actor, authorize=_allow)
    calls = []

    def validator(*, target_pk, organization):
        calls.append((target_pk, organization.pk))
        return TargetValidation(exists=True, organization_matches=True)

    values = {
        "run_id": run.pk,
        "actor": actor,
        "authorize": _allow,
        "entity_type": "student",
        "legacy_pk": "1001",
        "source_row_hash": SHA_B,
        "state": LegacyEntityMap.State.MIGRATED,
        "target_model_label": "accounts.profile",
        "target_validators": {"accounts.profile": validator},
    }
    first = upsert_entity_map(target_pk="42", **values)
    second = upsert_entity_map(target_pk="42", **values)

    assert first.pk == second.pk
    assert second.target_pk == "42"
    assert calls == [("42", organization.pk), ("42", organization.pk)]
    assert LegacyEntityMap.objects.count() == 1
    assert LegacyEntityObservation.objects.count() == 1

    with pytest.raises(LegacyLedgerConflictError) as exc_info:
        upsert_entity_map(target_pk="43", **values)
    assert exc_info.value.code == "legacy_entity_identity_conflict"
    assert LegacyEntityMap.objects.get().target_pk == "42"
    assert LegacyEntityObservation.objects.count() == 1


@pytest.mark.django_db
def test_issue_map_scope_mismatch_is_rejected_by_service(
    organization_actor,
    other_organization_actor,
):
    organization, actor = organization_actor
    other_organization, other_actor = other_organization_actor
    first_run = _create_run(organization, actor)
    second_run = _create_run(
        other_organization,
        other_actor,
        source_system="other_legacy",
        snapshot_sha256="c" * 64,
    )
    start_run(run_id=first_run.pk, actor=actor, authorize=_allow)
    start_run(run_id=second_run.pk, actor=other_actor, authorize=_allow)
    first_map = _migrate_one(first_run, actor)

    with pytest.raises(LegacyLedgerConflictError) as exc_info:
        upsert_issue(
            run_id=second_run.pk,
            actor=other_actor,
            authorize=_allow,
            source_table="students",
            entity_type="student",
            legacy_pk="1001",
            rule_code="missing-fin",
            severity=LegacyMigrationIssue.Severity.ERROR,
            payload_digest=SHA_A,
            entity_map_id=first_map.pk,
        )

    assert exc_info.value.code == "legacy_issue_map_scope_mismatch"
    assert LegacyMigrationIssue.objects.count() == 0


@pytest.mark.django_db
def test_issue_upsert_is_digest_safe_and_severity_is_monotonic(organization_actor):
    organization, actor = organization_actor
    run = _create_run(organization, actor)
    start_run(run_id=run.pk, actor=actor, authorize=_allow)
    values = {
        "run_id": run.pk,
        "actor": actor,
        "authorize": _allow,
        "source_table": "students",
        "entity_type": "student",
        "legacy_pk": "1001",
        "rule_code": "missing-fin",
        "payload_digest": SHA_A,
    }
    first = upsert_issue(severity=LegacyMigrationIssue.Severity.WARNING, **values)
    second = upsert_issue(severity=LegacyMigrationIssue.Severity.ERROR, **values)
    third = upsert_issue(severity=LegacyMigrationIssue.Severity.INFO, **values)

    assert first.pk == second.pk == third.pk
    assert third.severity == LegacyMigrationIssue.Severity.ERROR
    assert third.review_status == LegacyMigrationIssue.ReviewStatus.OPEN
    with pytest.raises(LegacyLedgerConflictError) as exc_info:
        upsert_issue(
            severity=LegacyMigrationIssue.Severity.ERROR,
            **{**values, "payload_digest": SHA_B},
        )
    assert exc_info.value.code == "legacy_issue_identity_conflict"


@pytest.mark.django_db
def test_issue_severity_escalation_reopens_prior_resolution(organization_actor):
    organization, actor = organization_actor
    run = _create_run(organization, actor)
    start_run(run_id=run.pk, actor=actor, authorize=_allow)
    values = {
        "run_id": run.pk,
        "actor": actor,
        "authorize": _allow,
        "source_table": "students",
        "entity_type": "student",
        "legacy_pk": "1001",
        "rule_code": "missing-fin",
        "payload_digest": SHA_A,
    }
    issue = upsert_issue(severity=LegacyMigrationIssue.Severity.WARNING, **values)
    review_issue(
        issue_id=issue.pk,
        actor=actor,
        authorize=_allow,
        decision=LegacyMigrationIssue.ReviewStatus.RESOLVED,
        reason_code="validated-source",
        evidence_digest=SHA_B,
    )

    escalated = upsert_issue(
        severity=LegacyMigrationIssue.Severity.ERROR,
        **values,
    )

    assert escalated.severity == LegacyMigrationIssue.Severity.ERROR
    assert escalated.review_status == LegacyMigrationIssue.ReviewStatus.OPEN


@pytest.mark.django_db
def test_success_uses_exact_derived_counts(organization_actor):
    organization, actor = organization_actor
    run = _create_run(organization, actor, source_row_count=2)
    start_run(run_id=run.pk, actor=actor, authorize=_allow)
    _migrate_one(run, actor)
    upsert_entity_map(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        entity_type="student",
        legacy_pk="1002",
        source_row_hash="c" * 64,
        state=LegacyEntityMap.State.SKIPPED,
        reconciliation_status=LegacyEntityMap.ReconciliationStatus.NOT_APPLICABLE,
        target_validators={},
    )

    finished = finish_run(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        outcome=LegacyMigrationRun.Status.SUCCEEDED,
    )

    assert finished.status == LegacyMigrationRun.Status.SUCCEEDED
    assert finished.migrated_count == 1
    assert finished.skipped_count == 1
    assert finished.quarantined_count == 0
    assert finished.failure_code == ""
    assert finished.finished_at >= finished.started_at


@pytest.mark.django_db
def test_second_rehearsal_preserves_first_run_observation(organization_actor):
    organization, actor = organization_actor
    first_run = _create_run(organization, actor)
    start_run(run_id=first_run.pk, actor=actor, authorize=_allow)
    first_map = _migrate_one(first_run, actor, target_pk="42")
    finish_run(
        run_id=first_run.pk,
        actor=actor,
        authorize=_allow,
        outcome=LegacyMigrationRun.Status.SUCCEEDED,
    )
    second_run = _create_run(organization, actor)
    start_run(run_id=second_run.pk, actor=actor, authorize=_allow)
    second_map = _migrate_one(second_run, actor, target_pk="42")

    first_map.refresh_from_db()
    assert first_map.pk == second_map.pk
    assert first_map.created_run_id == first_run.pk
    assert first_map.target_pk == "42"
    assert second_map.created_run_id == first_run.pk
    assert LegacyEntityMap.objects.count() == 1
    assert LegacyEntityObservation.objects.filter(run=first_run, entity_map=first_map).count() == 1
    assert LegacyEntityObservation.objects.filter(run=second_run, entity_map=second_map).count() == 1

    with pytest.raises(LegacyLedgerConflictError) as exc_info:
        _migrate_one(second_run, actor, target_pk="43")
    assert exc_info.value.code == "legacy_entity_identity_conflict"


@pytest.mark.django_db
def test_success_rejects_missing_classification_and_failure_code(organization_actor):
    organization, actor = organization_actor
    run = _create_run(organization, actor, source_row_count=2)
    start_run(run_id=run.pk, actor=actor, authorize=_allow)
    _migrate_one(run, actor)

    with pytest.raises(LegacyLedgerTransitionError) as exc_info:
        finish_run(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            outcome=LegacyMigrationRun.Status.SUCCEEDED,
            failure_code="unexpected-failure",
        )

    assert exc_info.value.code == "legacy_success_failure_code_forbidden"
    run.refresh_from_db()
    assert run.status == LegacyMigrationRun.Status.RUNNING

    with pytest.raises(LegacyLedgerTransitionError) as exc_info:
        finish_run(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            outcome=LegacyMigrationRun.Status.SUCCEEDED,
        )
    assert exc_info.value.code == "legacy_success_count_mismatch"


@pytest.mark.django_db
def test_success_rejects_unresolved_error_or_critical_issue(organization_actor):
    organization, actor = organization_actor
    run = _create_run(organization, actor)
    start_run(run_id=run.pk, actor=actor, authorize=_allow)
    _migrate_one(run, actor)
    upsert_issue(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        source_table="students",
        entity_type="student",
        legacy_pk="1001",
        rule_code="orphan-target",
        severity=LegacyMigrationIssue.Severity.CRITICAL,
        payload_digest=SHA_A,
    )

    with pytest.raises(LegacyLedgerTransitionError) as exc_info:
        finish_run(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            outcome=LegacyMigrationRun.Status.SUCCEEDED,
        )

    assert exc_info.value.code == "legacy_success_has_blocking_issue"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "outcome",
    [LegacyMigrationRun.Status.FAILED, LegacyMigrationRun.Status.CANCELLED],
)
def test_non_success_terminal_status_requires_safe_code(
    organization_actor,
    outcome,
):
    organization, actor = organization_actor
    run = _create_run(organization, actor)
    start_run(run_id=run.pk, actor=actor, authorize=_allow)

    with pytest.raises(LegacyLedgerTransitionError) as exc_info:
        finish_run(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            outcome=outcome,
        )
    assert exc_info.value.code == "legacy_terminal_failure_code_required"

    finished = finish_run(
        run_id=run.pk,
        actor=actor,
        authorize=_allow,
        outcome=outcome,
        failure_code="operator-stop",
    )
    assert finished.failure_code == "operator-stop"
    assert finished.finished_at is not None


@pytest.mark.django_db
def test_non_postgresql_fallback_rejects_busy_scope(organization_actor):
    organization, actor = organization_actor
    run = _create_run(organization, actor)
    if connection.vendor == "postgresql":
        pytest.skip("Process fallback is for non-PostgreSQL test databases")

    with ledger_locks._process_scope_lock(ledger._scope_parts(run)):
        with pytest.raises(LegacyLedgerBusyError) as exc_info:
            start_run(run_id=run.pk, actor=actor, authorize=_allow)

    assert exc_info.value.code == "legacy_scope_busy"


@pytest.mark.postgres
@pytest.mark.django_db
def test_postgresql_advisory_lock_rejects_busy_scope(organization_actor):
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL advisory lock test requires PostgreSQL")
    organization, actor = organization_actor
    # Direct pristine insert avoids retaining create_run's xact advisory lock
    # inside pytest-django's outer transaction.
    run = LegacyMigrationRun.objects.create(
        organization=organization,
        source_system="myedu_mariadb",
        snapshot_sha256=SHA_A,
        snapshot_size_bytes=100,
        source_row_count=1,
        schema_version="legacy-v1",
        transform_version="transform-v1",
        mode=LegacyMigrationRun.Mode.REHEARSAL,
        initiated_by=actor,
    )
    key = ledger.advisory_lock_key(
        organization_id=run.organization_id,
        source_system=run.source_system,
        snapshot_sha256=run.snapshot_sha256,
        transform_version=run.transform_version,
    )
    external_connection = connection.Database.connect(**connection.get_connection_params())
    external_connection.autocommit = True
    try:
        with external_connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_lock(%s)", [key])
        with pytest.raises(LegacyLedgerBusyError) as exc_info:
            start_run(run_id=run.pk, actor=actor, authorize=_allow)
        assert exc_info.value.code == "legacy_scope_busy"
    finally:
        with external_connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
        external_connection.close()


def test_advisory_key_is_deterministic_signed_64_bit():
    values = {
        "organization_id": "org-1",
        "source_system": "myedu_mariadb",
        "snapshot_sha256": SHA_A,
        "transform_version": "transform-v1",
    }

    first = ledger.advisory_lock_key(**values)
    second = ledger.advisory_lock_key(**values)
    changed = ledger.advisory_lock_key(**{**values, "transform_version": "transform-v2"})

    assert first == second
    assert first != changed
    assert -(2**63) <= first < 2**63


def test_issue_api_and_ledger_models_have_no_raw_context_fields():
    parameters = set(inspect.signature(upsert_issue).parameters)
    model_fields = {
        field.name
        for model in (LegacyMigrationRun, LegacyEntityMap, LegacyMigrationIssue)
        for field in model._meta.get_fields()
    }
    forbidden = {
        "context",
        "database_url",
        "dsn",
        "error_message",
        "password",
        "raw_context",
        "raw_payload",
        "raw_row",
        "source_path",
    }

    assert parameters.isdisjoint(forbidden)
    assert model_fields.isdisjoint(forbidden)
