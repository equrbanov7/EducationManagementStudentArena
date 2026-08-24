"""PostgreSQL regression for 0005 forward/reverse with existing ledger data."""

from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase

import pytest

from apps.legacy_import.models import (
    LegacyEntityMap,
    LegacyEntityMapVersion,
    LegacyEntityObservation,
    LegacyMigrationIssue,
    LegacyMigrationRun,
)
from apps.legacy_import.services.ledger import TargetValidation, create_run, start_run, upsert_entity_map, upsert_issue
from apps.legacy_import.services.review import review_and_remap_entity, review_issue
from apps.organizations.models import Organization
from core.constants import OrganizationType

pytestmark = pytest.mark.postgres
User = get_user_model()


def _allow(**_kwargs):
    return True


@pytest.mark.skipif(connection.vendor != "postgresql", reason="Migration rollback PostgreSQL-də yoxlanır.")
class ReviewedMappingMigrationRollbackTests(TransactionTestCase):
    reset_sequences = True
    migrate_from = ("legacy_import", "0005_reviewed_mapping_versions")
    migrate_to = ("legacy_import", "0004_lifecycle_guards")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        self.latest_targets = executor.loader.graph.leaf_nodes()
        executor.migrate([self.migrate_from])
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence('auth_user', 'id'), "
                "GREATEST((SELECT COALESCE(MAX(id), 1) FROM auth_user), 1))"
            )

    def _fixture_teardown(self):
        # Ledger rows are deliberately non-deletable in normal operation.
        # This is an isolated test DB cleanup before Django's global flush.
        MigrationExecutor(connection).migrate(self.latest_targets)
        with connection.cursor() as cursor:
            for table in (
                "legacy_import_legacyentityobservation",
                "legacy_import_legacyentitymapversion",
                "legacy_import_legacymigrationissue",
                "legacy_import_legacyentitymap",
                "legacy_import_legacymigrationrun",
            ):
                cursor.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")
            cursor.execute("DELETE FROM legacy_import_legacyentityobservation")
            cursor.execute("DELETE FROM legacy_import_legacyentitymapversion")
            cursor.execute("DELETE FROM legacy_import_legacymigrationissue")
            cursor.execute("DELETE FROM legacy_import_legacyentitymap")
            cursor.execute("DELETE FROM legacy_import_legacymigrationrun")
        MigrationExecutor(connection).migrate([("legacy_import", "0001_initial")])
        super()._fixture_teardown()
        MigrationExecutor(connection).migrate(self.latest_targets)

    def test_reverse_and_reapply_preserve_base_ledger_rows(self):
        actor = User.objects.create_user("legacy_migration_reviewer", password="test-only")
        organization = Organization.objects.create(
            name="Legacy migration rollback org",
            slug="legacy-migration-rollback-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=actor,
            status="active",
            is_active=True,
        )
        run = create_run(
            actor=actor,
            authorize=_allow,
            organization=organization,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=100,
            source_row_count=1,
            schema_version="legacy-v1",
            transform_version="transform-v1",
            mode=LegacyMigrationRun.Mode.REHEARSAL,
        )
        run = start_run(run_id=run.pk, actor=actor, authorize=_allow)
        entity_map = upsert_entity_map(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            entity_type="student",
            legacy_pk="1001",
            source_row_hash="b" * 64,
            state=LegacyEntityMap.State.MIGRATED,
            target_model_label="accounts.profile",
            target_pk="42",
            target_validators={
                "accounts.profile": lambda **_kwargs: TargetValidation(
                    exists=True,
                    organization_matches=True,
                )
            },
        )
        observation_id = LegacyEntityObservation.objects.get(run=run, entity_map=entity_map).pk
        self.assertEqual(LegacyEntityMapVersion.objects.filter(entity_map=entity_map).count(), 1)

        MigrationExecutor(connection).migrate([self.migrate_to])
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM legacy_import_legacyentitymap WHERE id = %s", [entity_map.pk])
            self.assertEqual(cursor.fetchone(), (1,))
            cursor.execute("SELECT COUNT(*) FROM legacy_import_legacyentityobservation WHERE id = %s", [observation_id])
            self.assertEqual(cursor.fetchone(), (1,))
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND table_name = 'legacy_import_legacyentityobservation' "
                "AND column_name = 'map_version_id'"
            )
            self.assertEqual(cursor.fetchone(), (0,))
            cursor.execute(
                "SELECT routine_name FROM information_schema.routine_privileges "
                "WHERE specific_schema = 'public' AND grantee = 'PUBLIC' "
                "AND privilege_type = 'EXECUTE' "
                "AND routine_name = ANY(%s)",
                [["legacy_import_issue_integrity_guard", "legacy_import_observation_integrity_guard"]],
            )
            self.assertEqual(cursor.fetchall(), [])

        MigrationExecutor(connection).migrate([self.migrate_from])
        version = LegacyEntityMapVersion.objects.get(entity_map_id=entity_map.pk, version_number=1)
        observation = LegacyEntityObservation.objects.get(pk=observation_id)
        self.assertEqual(version.target_pk, "42")
        self.assertEqual(observation.map_version_id, version.pk)
        self.assertEqual(observation.target_pk, "42")

    def test_reverse_stops_before_destroying_reviewed_remap_history(self):
        actor = User.objects.create_user("legacy_remap_rollback_reviewer", password="test-only")
        organization = Organization.objects.create(
            name="Legacy remap rollback org",
            slug="legacy-remap-rollback-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=actor,
            status="active",
            is_active=True,
        )

        def running_run(transform_version):
            run = create_run(
                actor=actor,
                authorize=_allow,
                organization=organization,
                source_system="myedu_mariadb",
                snapshot_sha256="a" * 64,
                snapshot_size_bytes=100,
                source_row_count=1,
                schema_version="legacy-v1",
                transform_version=transform_version,
                mode=LegacyMigrationRun.Mode.REHEARSAL,
            )
            return start_run(run_id=run.pk, actor=actor, authorize=_allow)

        first_run = running_run("transform-v1")
        entity_map = upsert_entity_map(
            run_id=first_run.pk,
            actor=actor,
            authorize=_allow,
            entity_type="student",
            legacy_pk="1001",
            source_row_hash="b" * 64,
            state=LegacyEntityMap.State.MIGRATED,
            target_model_label="accounts.profile",
            target_pk="42",
            target_validators={
                "accounts.profile": lambda **_kwargs: TargetValidation(
                    exists=True,
                    organization_matches=True,
                )
            },
        )
        second_run = running_run("transform-v2")
        issue = upsert_issue(
            run_id=second_run.pk,
            actor=actor,
            authorize=_allow,
            source_table="students",
            entity_type=entity_map.entity_type,
            legacy_pk=entity_map.legacy_pk,
            rule_code="legacy_entity_identity_conflict",
            severity="error",
            payload_digest="c" * 64,
            entity_map_id=entity_map.pk,
        )
        review_issue(
            issue_id=issue.pk,
            actor=actor,
            authorize=_allow,
            decision="resolved",
            reason_code="approved-remap",
            evidence_digest="d" * 64,
        )
        review_and_remap_entity(
            issue_id=issue.pk,
            actor=actor,
            authorize=_allow,
            source_row_hash="b" * 64,
            state=LegacyEntityMap.State.MIGRATED,
            target_model_label="accounts.profile",
            target_pk="43",
            target_validators={
                "accounts.profile": lambda **_kwargs: TargetValidation(
                    exists=True,
                    organization_matches=True,
                )
            },
        )
        self.assertEqual(LegacyEntityMapVersion.objects.filter(entity_map=entity_map).count(), 2)

        with self.assertRaisesRegex(RuntimeError, "reverse_blocked_by_review_history"):
            MigrationExecutor(connection).migrate([self.migrate_to])

        self.assertEqual(LegacyEntityMapVersion.objects.filter(entity_map=entity_map).count(), 2)
        self.assertEqual(LegacyEntityObservation.objects.filter(entity_map=entity_map).count(), 2)
        self.assertTrue(
            MigrationRecorder(connection)
            .migration_qs.filter(app="legacy_import", name="0005_reviewed_mapping_versions")
            .exists()
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND table_name = 'legacy_import_legacyentityobservation' "
                "AND column_name = 'map_version_id'"
            )
            self.assertEqual(cursor.fetchone(), ("NO",))
        initial = LegacyEntityMapVersion.objects.get(entity_map=entity_map, version_number=1)
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                LegacyEntityMapVersion.objects.filter(pk=initial.pk).update(target_pk="forged")

    def test_reverse_stops_for_review_evidence_even_without_remap(self):
        actor = User.objects.create_user("legacy_issue_rollback_reviewer", password="test-only")
        organization = Organization.objects.create(
            name="Legacy issue rollback org",
            slug="legacy-issue-rollback-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=actor,
            status="active",
            is_active=True,
        )
        run = create_run(
            actor=actor,
            authorize=_allow,
            organization=organization,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=100,
            source_row_count=0,
            schema_version="legacy-v1",
            transform_version="transform-v1",
            mode=LegacyMigrationRun.Mode.REHEARSAL,
        )
        run = start_run(run_id=run.pk, actor=actor, authorize=_allow)
        issue = upsert_issue(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            source_table="students",
            entity_type="student",
            legacy_pk="1001",
            rule_code="manual-review",
            severity="warning",
            payload_digest="b" * 64,
        )
        review_issue(
            issue_id=issue.pk,
            actor=actor,
            authorize=_allow,
            decision="acknowledged",
            reason_code="operator-ack",
            evidence_digest="c" * 64,
        )
        self.assertFalse(LegacyEntityMapVersion.objects.filter(version_number__gt=1).exists())

        with self.assertRaisesRegex(RuntimeError, "reverse_blocked_by_review_history"):
            MigrationExecutor(connection).migrate([self.migrate_to])

        issue.refresh_from_db()
        self.assertEqual(issue.review_status, LegacyMigrationIssue.ReviewStatus.ACKNOWLEDGED)
        self.assertEqual(issue.reviewed_by_id, actor.pk)
