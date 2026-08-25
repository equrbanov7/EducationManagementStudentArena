from unittest.mock import patch

from django.db import IntegrityError, connection
from django.db.models.signals import post_save

import pytest

from apps.legacy_import.models import LegacyImportBatch, LegacyMigrationRun
from apps.legacy_import.services.batch_accounting import (
    LegacyBatchConflictError,
    record_batch,
    verify_batch_chains,
)
from apps.legacy_import.services.ledger import (
    LegacyLedgerAuthorizationError,
    LegacyLedgerTransitionError,
    create_run,
    finish_run,
    start_run,
)
from apps.organizations.models import Organization
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def _allow(**_kwargs):
    return True


@pytest.fixture()
def organization_actor(db, django_user_model):
    actor = django_user_model.objects.create_user(
        username="batch_actor",
        email="batch-actor@example.test",
        password="test-only",
    )
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        organization = Organization.objects.create(
            name="Batch Accounting Organization",
            slug="batch-accounting-organization",
            org_type=OrganizationType.UNIVERSITY,
            owner=actor,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return organization, actor


def _running_run(organization, actor, *, source_row_count=3):
    run = create_run(
        actor=actor,
        authorize=_allow,
        organization=organization,
        source_system="myedu_mariadb",
        snapshot_sha256=SHA_A,
        snapshot_size_bytes=100,
        source_row_count=source_row_count,
        schema_version="schema-v1",
        transform_version="transform-v1",
        mode=LegacyMigrationRun.Mode.REHEARSAL,
        accounting_mode=LegacyMigrationRun.AccountingMode.BATCH,
    )
    return start_run(run_id=run.pk, actor=actor, authorize=_allow)


def _record(run, actor, **overrides):
    values = {
        "run_id": run.pk,
        "actor": actor,
        "authorize": _allow,
        "source_table": "students",
        "entity_type": "student",
        "sequence": 1,
        "first_legacy_pk": 10,
        "last_legacy_pk": 11,
        "migrated_count": 1,
        "skipped_count": 0,
        "quarantined_count": 1,
        "contract_fingerprint": SHA_B,
        "source_digest": SHA_C,
        "classification_digest": SHA_D,
        "target_digest": SHA_A,
    }
    values.update(overrides)
    return record_batch(**values)


@pytest.mark.django_db
def test_exact_retry_is_noop_and_different_retry_conflicts(organization_actor):
    organization, actor = organization_actor
    run = _running_run(organization, actor, source_row_count=2)

    first = _record(run, actor)
    retry = _record(run, actor)

    assert retry.pk == first.pk
    assert LegacyImportBatch.objects.count() == 1
    with pytest.raises(LegacyBatchConflictError) as exc_info:
        _record(run, actor, target_digest=SHA_D)
    assert exc_info.value.code == "legacy_batch_retry_conflict"
    assert LegacyImportBatch.objects.count() == 1


@pytest.mark.django_db
def test_batch_chain_is_monotonic_and_contract_stable(organization_actor):
    organization, actor = organization_actor
    run = _running_run(organization, actor, source_row_count=3)
    first = _record(run, actor, migrated_count=2, quarantined_count=0)

    second = _record(
        run,
        actor,
        sequence=2,
        first_legacy_pk=20,
        last_legacy_pk=20,
        migrated_count=0,
        skipped_count=1,
        quarantined_count=0,
    )

    assert second.previous_chain_digest == first.chain_digest
    assert second.chain_digest != first.chain_digest
    verify_batch_chains(run)

    with pytest.raises(LegacyBatchConflictError) as overlap:
        _record(
            run,
            actor,
            sequence=3,
            first_legacy_pk=20,
            last_legacy_pk=21,
        )
    assert overlap.value.code == "legacy_batch_pk_overlap"

    with pytest.raises(LegacyBatchConflictError) as contract_change:
        _record(
            run,
            actor,
            sequence=3,
            first_legacy_pk=30,
            last_legacy_pk=31,
            contract_fingerprint=SHA_C,
        )
    assert contract_change.value.code == "legacy_batch_contract_changed"


@pytest.mark.django_db
def test_gap_and_entity_type_change_are_rejected(organization_actor):
    organization, actor = organization_actor
    run = _running_run(organization, actor, source_row_count=3)
    _record(run, actor)

    with pytest.raises(LegacyBatchConflictError) as missing:
        _record(run, actor, sequence=3, first_legacy_pk=30, last_legacy_pk=31)
    assert missing.value.code == "legacy_batch_predecessor_missing"

    with pytest.raises(LegacyBatchConflictError) as changed:
        _record(
            run,
            actor,
            sequence=2,
            first_legacy_pk=20,
            last_legacy_pk=20,
            migrated_count=1,
            quarantined_count=0,
            entity_type="worker",
        )
    assert changed.value.code == "legacy_batch_entity_type_changed"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"sequence": 0}, "legacy_batch_sequence_invalid"),
        ({"first_legacy_pk": 0}, "legacy_batch_first_pk_invalid"),
        ({"last_legacy_pk": 0}, "legacy_batch_last_pk_invalid"),
        (
            {"first_legacy_pk": 20, "last_legacy_pk": 10},
            "legacy_batch_pk_range_invalid",
        ),
        (
            {"first_legacy_pk": 10, "last_legacy_pk": 10},
            "legacy_batch_count_exceeds_pk_range",
        ),
        (
            {"migrated_count": 0, "quarantined_count": 0},
            "legacy_batch_empty",
        ),
    ],
)
def test_invalid_batch_shape_is_rejected_before_write(organization_actor, overrides, code):
    organization, actor = organization_actor
    run = _running_run(organization, actor, source_row_count=2)

    with pytest.raises(LegacyBatchConflictError) as exc_info:
        _record(run, actor, **overrides)

    assert exc_info.value.code == code
    assert not LegacyImportBatch.objects.exists()


@pytest.mark.django_db
def test_authorization_and_active_actor_are_required(organization_actor):
    organization, actor = organization_actor
    run = _running_run(organization, actor, source_row_count=2)

    with pytest.raises(LegacyLedgerAuthorizationError) as denied:
        _record(run, actor, authorize=lambda **_kwargs: False)
    assert denied.value.code == "legacy_authorization_denied"

    actor.is_active = False
    actor.save(update_fields=["is_active"])
    with pytest.raises(LegacyLedgerAuthorizationError) as inactive:
        _record(run, actor)
    assert inactive.value.code == "legacy_batch_actor_required"
    assert not LegacyImportBatch.objects.exists()


@pytest.mark.django_db
def test_row_accounting_run_rejects_batch_evidence(organization_actor):
    organization, actor = organization_actor
    run = create_run(
        actor=actor,
        authorize=_allow,
        organization=organization,
        source_system="myedu_mariadb",
        snapshot_sha256=SHA_A,
        snapshot_size_bytes=100,
        source_row_count=2,
        schema_version="schema-v1",
        transform_version="transform-v1",
        mode=LegacyMigrationRun.Mode.REHEARSAL,
    )
    run = start_run(run_id=run.pk, actor=actor, authorize=_allow)

    with pytest.raises(LegacyBatchConflictError) as exc_info:
        _record(run, actor)

    assert exc_info.value.code == "legacy_batch_accounting_mode_required"
    assert not LegacyImportBatch.objects.exists()


@pytest.mark.django_db
def test_successful_run_uses_batch_counts(organization_actor):
    organization, actor = organization_actor
    run = _running_run(organization, actor, source_row_count=3)
    _record(run, actor, migrated_count=1, quarantined_count=1)
    _record(
        run,
        actor,
        source_table="workers",
        entity_type="worker",
        first_legacy_pk=100,
        last_legacy_pk=100,
        migrated_count=0,
        skipped_count=1,
        quarantined_count=0,
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
    assert finished.quarantined_count == 1


@pytest.mark.django_db
def test_success_requires_complete_batch_accounting(organization_actor):
    organization, actor = organization_actor
    run = _running_run(organization, actor, source_row_count=3)
    _record(run, actor)

    with pytest.raises(LegacyLedgerTransitionError) as exc_info:
        finish_run(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            outcome=LegacyMigrationRun.Status.SUCCEEDED,
        )

    assert exc_info.value.code == "legacy_success_count_mismatch"
    run.refresh_from_db()
    assert run.status == LegacyMigrationRun.Status.RUNNING


@pytest.mark.django_db
@pytest.mark.skipif(
    connection.vendor != "sqlite",
    reason=(
        "The raw tamper UPDATE is blocked by the PostgreSQL batch-immutability trigger; "
        "PG-side chain tampering is covered by test_rehearsal_postgres."
        "test_batch_chain_verifies_and_finish_run_is_fail_closed."
    ),
)
def test_python_chain_verification_detects_tampering_on_sqlite(organization_actor):
    organization, actor = organization_actor
    run = _running_run(organization, actor, source_row_count=2)
    batch = _record(run, actor)
    LegacyImportBatch.objects.filter(pk=batch.pk).update(chain_digest=SHA_B)

    with pytest.raises(LegacyBatchConflictError) as exc_info:
        verify_batch_chains(run)

    assert exc_info.value.code == "legacy_batch_digest_invalid"


@pytest.mark.django_db
def test_database_integrity_error_is_sanitized(organization_actor):
    organization, actor = organization_actor
    run = _running_run(organization, actor, source_row_count=2)

    with patch.object(
        LegacyImportBatch,
        "save",
        side_effect=IntegrityError("sensitive-driver-detail"),
    ):
        with pytest.raises(LegacyBatchConflictError) as exc_info:
            _record(run, actor)

    assert exc_info.value.code == "legacy_batch_validation_failed"
    assert str(exc_info.value) == "legacy_batch_validation_failed"
    assert "sensitive-driver-detail" not in str(exc_info.value)
    assert not LegacyImportBatch.objects.exists()
