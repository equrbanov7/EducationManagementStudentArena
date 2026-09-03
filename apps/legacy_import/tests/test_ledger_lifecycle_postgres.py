"""Defense-in-depth tests for direct PostgreSQL ledger writes."""

from django.db import DatabaseError, connection, transaction
from django.db.models.signals import post_save
from django.utils import timezone

import pytest

from apps.legacy_import.models import (
    LegacyEntityMap,
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

pytestmark = [pytest.mark.postgres, pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _postgresql_only():
    if connection.vendor != "postgresql":
        pytest.skip("Lifecycle DB guards require PostgreSQL")


@pytest.fixture()
def organization_actor(django_user_model):
    owner = django_user_model.objects.create_user(
        username="lifecycle_owner",
        email="lifecycle-owner@example.test",
        password="test-only",
    )
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        organization = Organization.objects.create(
            name="Lifecycle Organization",
            slug="lifecycle-organization",
            org_type=OrganizationType.UNIVERSITY,
            owner=owner,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return organization, owner


def _pending_run(organization, actor, *, source_row_count=1):
    return LegacyMigrationRun.objects.create(
        organization=organization,
        source_system="myedu_mariadb",
        snapshot_sha256=SHA_A,
        snapshot_size_bytes=100,
        source_row_count=source_row_count,
        schema_version="legacy-v1",
        transform_version="transform-v1",
        mode=LegacyMigrationRun.Mode.REHEARSAL,
        initiated_by=actor,
    )


def _start(run):
    updated = LegacyMigrationRun.objects.filter(pk=run.pk).update(
        status=LegacyMigrationRun.Status.RUNNING,
        started_at=timezone.now(),
    )
    assert updated == 1
    run.refresh_from_db()
    return run


def _map(run, *, state=LegacyEntityMap.State.MIGRATED):
    migrated = state == LegacyEntityMap.State.MIGRATED
    entity_map = LegacyEntityMap.objects.create(
        organization=run.organization,
        source_system=run.source_system,
        entity_type="student",
        legacy_pk="1001",
        source_row_hash=SHA_B,
        transform_version=run.transform_version,
        target_model_label="accounts.profile" if migrated else "",
        target_pk="42" if migrated else "",
        created_run=run,
        state=state,
    )
    version = ensure_initial_version(entity_map)
    LegacyEntityObservation.objects.create(
        organization=run.organization,
        run=run,
        entity_map=entity_map,
        map_version=version,
        source_row_hash=entity_map.source_row_hash,
        transform_version=entity_map.transform_version,
        target_model_label=entity_map.target_model_label,
        target_pk=entity_map.target_pk,
        state=entity_map.state,
        reconciliation_status=entity_map.reconciliation_status,
    )
    return entity_map


def _finish(run, *, status, migrated=0, skipped=0, quarantined=0, failure_code=""):
    return LegacyMigrationRun.objects.filter(pk=run.pk).update(
        status=status,
        finished_at=timezone.now(),
        migrated_count=migrated,
        skipped_count=skipped,
        quarantined_count=quarantined,
        failure_code=failure_code,
    )


def test_run_insert_and_transition_must_follow_pristine_lifecycle(organization_actor):
    organization, actor = organization_actor

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyMigrationRun.objects.create(
                organization=organization,
                source_system="forged_source",
                snapshot_sha256=SHA_A,
                snapshot_size_bytes=100,
                source_row_count=0,
                schema_version="legacy-v1",
                transform_version="transform-v1",
                mode=LegacyMigrationRun.Mode.REHEARSAL,
                initiated_by=actor,
                status=LegacyMigrationRun.Status.RUNNING,
                started_at=timezone.now(),
            )

    run = _pending_run(organization, actor)
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            _finish(
                run,
                status=LegacyMigrationRun.Status.SUCCEEDED,
                migrated=1,
            )
    run.refresh_from_db()
    assert run.status == LegacyMigrationRun.Status.PENDING


def test_run_source_count_and_initiator_are_immutable(
    organization_actor,
    django_user_model,
):
    organization, actor = organization_actor
    other_actor = django_user_model.objects.create_user(
        username="other_lifecycle_actor",
        email="other-lifecycle-actor@example.test",
        password="test-only",
    )
    run = _pending_run(organization, actor)

    for update in ({"source_row_count": 2}, {"initiated_by": other_actor}):
        with pytest.raises(DatabaseError):
            with transaction.atomic():
                LegacyMigrationRun.objects.filter(pk=run.pk).update(**update)


def test_only_one_running_run_is_allowed_per_source_scope(organization_actor):
    organization, actor = organization_actor
    first = _pending_run(organization, actor)
    second = _pending_run(organization, actor)
    _start(first)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            _start(second)

    second.refresh_from_db()
    assert second.status == LegacyMigrationRun.Status.PENDING


def test_map_write_requires_matching_running_run_and_stops_at_terminal(
    organization_actor,
):
    organization, actor = organization_actor
    run = _pending_run(organization, actor)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            _map(run, state=LegacyEntityMap.State.QUARANTINED)

    _start(run)
    entity_map = _map(run, state=LegacyEntityMap.State.QUARANTINED)
    assert (
        _finish(
            run,
            status=LegacyMigrationRun.Status.FAILED,
            quarantined=1,
            failure_code="validation-stop",
        )
        == 1
    )

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyEntityMap.objects.filter(pk=entity_map.pk).update(source_row_hash="c" * 64)
    observation = LegacyEntityObservation.objects.get(entity_map=entity_map, run=run)
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyEntityObservation.objects.filter(pk=observation.pk).update(source_row_hash="c" * 64)


def test_success_requires_exact_map_counts_and_no_unresolved_blocker(
    organization_actor,
):
    organization, actor = organization_actor
    run = _start(_pending_run(organization, actor))
    entity_map = _map(run)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            _finish(
                run,
                status=LegacyMigrationRun.Status.SUCCEEDED,
                migrated=0,
            )

    issue = LegacyMigrationIssue.objects.create(
        organization=organization,
        run=run,
        entity_map=entity_map,
        source_table="students",
        entity_type=entity_map.entity_type,
        legacy_pk=entity_map.legacy_pk,
        rule_code="orphan-target",
        severity=LegacyMigrationIssue.Severity.ERROR,
        payload_digest=SHA_A,
    )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            _finish(
                run,
                status=LegacyMigrationRun.Status.SUCCEEDED,
                migrated=1,
            )

    LegacyMigrationIssue.objects.filter(pk=issue.pk).update(
        review_status=LegacyMigrationIssue.ReviewStatus.RESOLVED,
        reviewed_by=actor,
        reviewed_at=timezone.now(),
        review_reason_code="validated-source",
        review_evidence_digest=SHA_B,
    )
    assert (
        _finish(
            run,
            status=LegacyMigrationRun.Status.SUCCEEDED,
            migrated=1,
        )
        == 1
    )
    run.refresh_from_db()
    assert run.status == LegacyMigrationRun.Status.SUCCEEDED


def test_terminal_run_is_immutable_but_issue_review_remains_available(
    organization_actor,
):
    organization, actor = organization_actor
    run = _start(_pending_run(organization, actor, source_row_count=0))
    issue = LegacyMigrationIssue.objects.create(
        organization=organization,
        run=run,
        source_table="students",
        entity_type="student",
        legacy_pk="1001",
        rule_code="manual-review",
        severity=LegacyMigrationIssue.Severity.WARNING,
        payload_digest=SHA_A,
    )
    assert (
        _finish(
            run,
            status=LegacyMigrationRun.Status.FAILED,
            failure_code="manual-stop",
        )
        == 1
    )

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyMigrationRun.objects.filter(pk=run.pk).update(failure_code="forged-change")
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyMigrationIssue.objects.filter(pk=issue.pk).update(
                review_status=LegacyMigrationIssue.ReviewStatus.ACKNOWLEDGED
            )
    assert (
        LegacyMigrationIssue.objects.filter(pk=issue.pk).update(
            review_status=LegacyMigrationIssue.ReviewStatus.ACKNOWLEDGED,
            reviewed_by=actor,
            reviewed_at=timezone.now(),
            review_reason_code="operator-ack",
            review_evidence_digest=SHA_B,
        )
        == 1
    )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyMigrationIssue.objects.filter(pk=issue.pk).update(
                severity=LegacyMigrationIssue.Severity.ERROR,
                review_status=LegacyMigrationIssue.ReviewStatus.OPEN,
            )


def test_version_history_rejects_direct_mutation_and_unreviewed_remap(organization_actor):
    organization, actor = organization_actor
    run = _start(_pending_run(organization, actor))
    entity_map = _map(run)
    initial = entity_map.versions.get(version_number=1)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            entity_map.versions.filter(pk=initial.pk).update(target_pk="forged-target")

    issue = LegacyMigrationIssue.objects.create(
        organization=organization,
        run=run,
        entity_map=entity_map,
        source_table="students",
        entity_type=entity_map.entity_type,
        legacy_pk=entity_map.legacy_pk,
        rule_code="manual-review",
        severity=LegacyMigrationIssue.Severity.ERROR,
        payload_digest=SHA_A,
    )
    reviewed_at = timezone.now()
    LegacyMigrationIssue.objects.filter(pk=issue.pk).update(
        review_status=LegacyMigrationIssue.ReviewStatus.RESOLVED,
        reviewed_by=actor,
        reviewed_at=reviewed_at,
        review_reason_code="approved-remap",
        review_evidence_digest=SHA_B,
    )
    with pytest.raises(DatabaseError):
        with transaction.atomic():
            entity_map.versions.create(
                organization=organization,
                version_number=2,
                supersedes=initial,
                recorded_run=run,
                source_row_hash=SHA_B,
                transform_version=run.transform_version,
                target_model_label="accounts.profile",
                target_pk="43",
                state=LegacyEntityMap.State.MIGRATED,
                approved_issue=issue,
                reviewed_by=actor,
                reviewed_at=reviewed_at,
                review_reason_code="approved-remap",
                review_evidence_digest=SHA_B,
                applied_by=actor,
            )


def test_direct_map_insert_gets_exact_initial_version(organization_actor):
    organization, actor = organization_actor
    run = _start(_pending_run(organization, actor))

    entity_map = LegacyEntityMap.objects.create(
        organization=organization,
        source_system=run.source_system,
        entity_type="student",
        legacy_pk="direct-version-check",
        source_row_hash=SHA_B,
        transform_version=run.transform_version,
        created_run=run,
        state=LegacyEntityMap.State.QUARANTINED,
    )

    version = entity_map.versions.get()
    assert version.version_number == 1
    assert version.recorded_run_id == run.pk
    assert version.source_row_hash == entity_map.source_row_hash
    assert version.state == entity_map.state


def test_security_definer_trigger_functions_are_not_publicly_executable():
    function_names = [
        "legacy_import_issue_integrity_guard",
        "legacy_import_version_integrity_guard",
        "legacy_import_initial_version_create",
        "legacy_import_observation_integrity_guard",
    ]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT routine_name FROM information_schema.routine_privileges "
            "WHERE specific_schema = 'public' AND grantee = 'PUBLIC' "
            "AND privilege_type = 'EXECUTE' AND routine_name = ANY(%s)",
            [function_names],
        )
        assert cursor.fetchall() == []


def test_running_issue_severity_escalation_must_reopen_review(organization_actor):
    organization, actor = organization_actor
    run = _start(_pending_run(organization, actor))
    issue = LegacyMigrationIssue.objects.create(
        organization=organization,
        run=run,
        source_table="students",
        entity_type="student",
        legacy_pk="1001",
        rule_code="manual-review",
        severity=LegacyMigrationIssue.Severity.WARNING,
        payload_digest=SHA_A,
    )
    LegacyMigrationIssue.objects.filter(pk=issue.pk).update(
        review_status=LegacyMigrationIssue.ReviewStatus.RESOLVED,
        reviewed_by=actor,
        reviewed_at=timezone.now(),
        review_reason_code="validated-source",
        review_evidence_digest=SHA_B,
    )

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            LegacyMigrationIssue.objects.filter(pk=issue.pk).update(severity=LegacyMigrationIssue.Severity.ERROR)
    assert (
        LegacyMigrationIssue.objects.filter(pk=issue.pk).update(
            severity=LegacyMigrationIssue.Severity.ERROR,
            review_status=LegacyMigrationIssue.ReviewStatus.OPEN,
        )
        == 1
    )
