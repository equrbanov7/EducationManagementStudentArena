from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError
from django.db.models.signals import post_save
from django.utils import timezone

import pytest

from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityMapVersion,
    LegacyEntityObservation,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.services.versioning import ensure_initial_version
from apps.organizations.models import Organization
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType

SHA_A = "a" * 64
SHA_B = "b" * 64


def _make_run(organization, **overrides):
    values = {
        "organization": organization,
        "source_system": "myedu_mariadb",
        "snapshot_sha256": SHA_A,
        "snapshot_size_bytes": 2_142_912_818,
        "source_row_count": 10,
        "schema_version": "legacy-v1",
        "transform_version": "transform-v1",
        "mode": LegacyMigrationRun.Mode.REHEARSAL,
    }
    values.update(overrides)
    return LegacyMigrationRun.objects.create(**values)


def _ensure_running(run):
    if run.status == LegacyMigrationRun.Status.PENDING:
        LegacyMigrationRun.objects.filter(pk=run.pk).update(
            status=LegacyMigrationRun.Status.RUNNING,
            started_at=timezone.now(),
        )
        run.refresh_from_db()


def _make_map(run, **overrides):
    _ensure_running(run)
    values = {
        "organization": run.organization,
        "source_system": run.source_system,
        "entity_type": "student",
        "legacy_pk": "1001",
        "source_row_hash": SHA_B,
        "transform_version": run.transform_version,
        "target_model_label": "auth.user",
        "target_pk": "42",
        "created_run": run,
        "state": LegacyEntityMap.State.MIGRATED,
    }
    values.update(overrides)
    entity_map = LegacyEntityMap.objects.create(**values)
    ensure_initial_version(entity_map)
    return entity_map


def _make_observation(run, entity_map, **overrides):
    values = {
        "organization": run.organization,
        "run": run,
        "entity_map": entity_map,
        "map_version": LegacyEntityMapVersion.objects.filter(entity_map=entity_map).order_by("-version_number").first(),
        "source_row_hash": entity_map.source_row_hash,
        "transform_version": entity_map.transform_version,
        "target_model_label": entity_map.target_model_label,
        "target_pk": entity_map.target_pk,
        "state": entity_map.state,
        "reconciliation_status": entity_map.reconciliation_status,
    }
    values.update(overrides)
    return LegacyEntityObservation.objects.create(**values)


def _make_organization(django_user_model, code):
    owner = django_user_model.objects.create_user(
        username=f"legacy_{code}_owner",
        email=f"legacy-{code}@example.test",
        password="test-only",
    )
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        return Organization.objects.create(
            name=f"Legacy {code.title()} Organization",
            slug=f"legacy-{code}-organization",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)


@pytest.fixture()
def organization(db, django_user_model):
    return _make_organization(django_user_model, "primary")


@pytest.fixture()
def other_organization(db, django_user_model):
    return _make_organization(django_user_model, "other")


@pytest.mark.django_db
def test_run_records_only_safe_provenance_and_count_fields(organization):
    run = _make_run(organization)

    assert run.pk is not None
    assert run.status == LegacyMigrationRun.Status.PENDING
    assert run.created_at is not None
    field_names = {field.name for field in run._meta.get_fields()}
    forbidden = {
        "dsn",
        "database_url",
        "password",
        "raw_payload",
        "raw_row",
        "error_message",
        "source_path",
    }
    assert field_names.isdisjoint(forbidden)


@pytest.mark.django_db
def test_run_rejects_dsn_shaped_source_and_invalid_digest(organization):
    run = _make_run(organization)
    run.source_system = "postgresql://secret-host/database"
    run.snapshot_sha256 = "not-a-digest"

    with pytest.raises(ValidationError) as exc_info:
        run.full_clean()

    assert {"source_system", "snapshot_sha256"}.issubset(exc_info.value.message_dict)


@pytest.mark.django_db
def test_run_classified_counts_cannot_exceed_source_total(organization):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _make_run(
                organization,
                source_row_count=1,
                migrated_count=1,
                skipped_count=1,
            )


@pytest.mark.django_db
def test_entity_map_source_identity_is_idempotent(organization):
    run = _make_run(organization)
    _make_map(run)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _make_map(run, source_row_hash="c" * 64, target_pk="43")


@pytest.mark.django_db
def test_entity_map_state_controls_target_reference(organization):
    run = _make_run(organization)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _make_map(run, state=LegacyEntityMap.State.QUARANTINED)


@pytest.mark.django_db
def test_observation_is_unique_per_run_and_canonical_map(organization):
    run = _make_run(organization)
    entity_map = _make_map(run)
    _make_observation(run, entity_map)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _make_observation(run, entity_map)


@pytest.mark.django_db
def test_observation_model_validation_rejects_mapping_drift(organization):
    run = _make_run(organization)
    entity_map = _make_map(run)
    observation = LegacyEntityObservation(
        organization=organization,
        run=run,
        entity_map=entity_map,
        map_version=LegacyEntityMapVersion.objects.get(entity_map=entity_map, version_number=1),
        source_row_hash="c" * 64,
        transform_version=entity_map.transform_version,
        target_model_label=entity_map.target_model_label,
        target_pk=entity_map.target_pk,
        state=entity_map.state,
        reconciliation_status=entity_map.reconciliation_status,
    )

    with pytest.raises(ValidationError) as exc_info:
        observation.full_clean()
    assert "map_version" in exc_info.value.message_dict


@pytest.mark.django_db
def test_entity_map_rejects_non_opaque_legacy_key(organization):
    run = _make_run(organization)
    entity_map = LegacyEntityMap(
        organization=organization,
        source_system=run.source_system,
        entity_type="student",
        legacy_pk="person@example.test",
        source_row_hash=SHA_B,
        transform_version=run.transform_version,
        created_run=run,
        state=LegacyEntityMap.State.QUARANTINED,
    )

    with pytest.raises(ValidationError) as exc_info:
        entity_map.full_clean()

    assert "legacy_pk" in exc_info.value.message_dict


@pytest.mark.django_db
def test_entity_map_model_validation_rejects_cross_organization_run(organization, other_organization):
    run = _make_run(organization)
    entity_map = LegacyEntityMap(
        organization=other_organization,
        source_system=run.source_system,
        entity_type="student",
        legacy_pk="1001",
        source_row_hash=SHA_B,
        transform_version=run.transform_version,
        created_run=run,
        state=LegacyEntityMap.State.QUARANTINED,
    )

    with pytest.raises(ValidationError) as exc_info:
        entity_map.full_clean()

    assert "created_run" in exc_info.value.message_dict


@pytest.mark.django_db
def test_sqlite_objects_create_does_not_claim_cross_table_scope_security(organization, other_organization):
    """SQLite cross-table CHECK yaza bilmir; production təminatı PG trigger-dir."""
    if connection.vendor != "sqlite":
        pytest.skip("Bu test yalnız SQLite limitation-ını sənədləşdirir")
    run = _make_run(organization)

    entity_map = LegacyEntityMap.objects.create(
        organization=other_organization,
        source_system="different_source",
        entity_type="student",
        legacy_pk="sqlite-limitation",
        source_row_hash=SHA_B,
        transform_version="different-transform",
        created_run=run,
        state=LegacyEntityMap.State.QUARANTINED,
    )

    assert entity_map.pk is not None
    with pytest.raises(ValidationError) as exc_info:
        entity_map.full_clean()
    assert {"created_run", "source_system", "transform_version"}.issubset(exc_info.value.message_dict)


@pytest.mark.django_db
def test_issue_identity_is_unique_within_run(organization):
    run = _make_run(organization)
    _ensure_running(run)
    values = {
        "organization": organization,
        "run": run,
        "source_table": "students",
        "entity_type": "student",
        "legacy_pk": "1001",
        "rule_code": "missing-fin",
        "severity": LegacyMigrationIssue.Severity.WARNING,
        "payload_digest": SHA_B,
    }
    LegacyMigrationIssue.objects.create(**values)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LegacyMigrationIssue.objects.create(**values)


@pytest.mark.django_db
def test_issue_model_validation_rejects_mismatched_map_identity(organization):
    run = _make_run(organization)
    entity_map = _make_map(run)
    issue = LegacyMigrationIssue(
        organization=organization,
        run=run,
        entity_map=entity_map,
        source_table="students",
        entity_type="student",
        legacy_pk="different-key",
        rule_code="missing-fin",
        severity=LegacyMigrationIssue.Severity.WARNING,
        payload_digest=SHA_A,
    )

    with pytest.raises(ValidationError) as exc_info:
        issue.full_clean()

    assert "entity_map" in exc_info.value.message_dict


@pytest.mark.django_db
def test_ledger_rows_cannot_be_deleted_through_models(organization):
    run = _make_run(organization)
    entity_map = _make_map(run)
    observation = _make_observation(run, entity_map)

    with pytest.raises(ProtectedError):
        run.delete()
    with pytest.raises(ProtectedError):
        LegacyMigrationRun.objects.filter(pk=run.pk).delete()
    with pytest.raises(ProtectedError):
        observation.delete()
    with pytest.raises(ProtectedError):
        LegacyEntityObservation.objects.filter(pk=observation.pk).delete()

    assert LegacyMigrationRun.objects.filter(pk=run.pk).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["mode", "status", "origin"])
def test_run_choice_constraints_reject_unknown_values(organization, field):
    run = _make_run(organization)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LegacyMigrationRun.objects.filter(pk=run.pk).update(**{field: "unknown-choice"})


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["state", "reconciliation_status"])
def test_entity_map_choice_constraints_reject_unknown_values(organization, field):
    run = _make_run(organization)
    entity_map = _make_map(run)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LegacyEntityMap.objects.filter(pk=entity_map.pk).update(**{field: "unknown-choice"})


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["state", "reconciliation_status"])
def test_observation_choice_constraints_reject_unknown_values(organization, field):
    run = _make_run(organization)
    entity_map = _make_map(run)
    observation = _make_observation(run, entity_map)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LegacyEntityObservation.objects.filter(pk=observation.pk).update(**{field: "unknown-choice"})


@pytest.mark.django_db
@pytest.mark.parametrize("field", ["severity", "review_status"])
def test_issue_choice_constraints_reject_unknown_values(organization, field):
    run = _make_run(organization)
    _ensure_running(run)
    issue = LegacyMigrationIssue.objects.create(
        organization=organization,
        run=run,
        source_table="students",
        entity_type="student",
        legacy_pk="1001",
        rule_code="missing-fin",
        severity=LegacyMigrationIssue.Severity.WARNING,
        payload_digest=SHA_B,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LegacyMigrationIssue.objects.filter(pk=issue.pk).update(**{field: "unknown-choice"})
