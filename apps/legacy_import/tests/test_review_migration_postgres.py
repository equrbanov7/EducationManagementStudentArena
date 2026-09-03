"""PostgreSQL regression for 0005 forward/reverse with existing ledger data."""

from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase
from django.utils import timezone

import pytest

from apps.legacy_import.models import LegacyEntityMapVersion, LegacyEntityObservation, LegacyMigrationIssue
from apps.organizations.models import Organization
from core.constants import OrganizationType

# Miqrasiya round-trip (migrate → sıfıra → geri) testləri xdist-də 4 worker-in
# paralel miqrasiyası altında 300 s qlobal limiti keçə bilir (Develop run
# 33778014237 flake-i); modul üçün limit ayrıca qaldırılır.
pytestmark = [pytest.mark.postgres, pytest.mark.timeout(1200)]
User = get_user_model()


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
        executor.loader.build_graph()
        # DB 0005-dədir, runtime modellər isə 0006 sxemini (accounting_mode)
        # gözləyir; ona görə ledger sətirləri 0005 project state-inin HISTORICAL
        # modelləri ilə yazılır. 0006 yalnız run cədvəlinə toxunduğundan
        # map/version/observation/issue üçün runtime modellə oxumaq təhlükəsizdir.
        self.old_apps = executor.loader.project_state(self.migrate_from).apps
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

    def _old_model(self, name):
        return self.old_apps.get_model("legacy_import", name)

    def _create_running_run(self, *, organization, actor, transform_version="transform-v1", source_row_count=1):
        """Servisdəki create_run + start_run axınının 0005-schema ekvivalenti."""
        run = self._old_model("LegacyMigrationRun").objects.create(
            organization_id=organization.pk,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=100,
            source_row_count=source_row_count,
            schema_version="legacy-v1",
            transform_version=transform_version,
            mode="rehearsal",
            origin="manual",
            initiated_by_id=actor.pk,
            status="pending",
            started_at=None,
            finished_at=None,
            migrated_count=0,
            skipped_count=0,
            quarantined_count=0,
            failure_code="",
        )
        run.status = "running"
        run.started_at = timezone.now()
        run.save()
        return run

    def _create_migrated_entity_map(self, *, run, organization, target_pk="42"):
        """upsert_entity_map ekvivalenti: map + trigger-yaradılmış v1 + observation."""
        entity_map = self._old_model("LegacyEntityMap").objects.create(
            organization_id=organization.pk,
            source_system=run.source_system,
            entity_type="student",
            legacy_pk="1001",
            source_row_hash="b" * 64,
            transform_version=run.transform_version,
            target_model_label="accounts.profile",
            target_pk=target_pk,
            created_run_id=run.pk,
            state="migrated",
            reconciliation_status="pending",
        )
        # 0005-in legacy_import_map_initial_version trigger-i v1-i özü yaradır.
        version = self._old_model("LegacyEntityMapVersion").objects.get(entity_map_id=entity_map.pk, version_number=1)
        observation = self._old_model("LegacyEntityObservation").objects.create(
            organization_id=organization.pk,
            run_id=run.pk,
            entity_map_id=entity_map.pk,
            map_version_id=version.pk,
            source_row_hash="b" * 64,
            transform_version=run.transform_version,
            target_model_label="accounts.profile",
            target_pk=target_pk,
            state="migrated",
            reconciliation_status="pending",
        )
        return entity_map, version, observation

    def _create_open_issue(self, *, run, organization, rule_code, severity, payload_digest, entity_map_id=None):
        return self._old_model("LegacyMigrationIssue").objects.create(
            organization_id=organization.pk,
            run_id=run.pk,
            entity_map_id=entity_map_id,
            source_table="students",
            entity_type="student",
            legacy_pk="1001",
            rule_code=rule_code,
            severity=severity,
            payload_digest=payload_digest,
            review_status="open",
        )

    def _review_issue(self, issue, *, actor, decision, reason_code, evidence_digest):
        """review_issue servis ekvivalenti: evidence-li status keçidi (UPDATE)."""
        issue.review_status = decision
        issue.reviewed_by_id = actor.pk
        issue.reviewed_at = timezone.now()
        issue.review_reason_code = reason_code
        issue.review_evidence_digest = evidence_digest
        issue.save()
        return issue

    def _apply_reviewed_remap(self, *, issue, run, entity_map, predecessor, actor, target_pk):
        """review_and_remap_entity ekvivalenti: v2 + onun observation-u."""
        version = self._old_model("LegacyEntityMapVersion").objects.create(
            organization_id=issue.organization_id,
            entity_map_id=entity_map.pk,
            version_number=predecessor.version_number + 1,
            supersedes_id=predecessor.pk,
            recorded_run_id=run.pk,
            source_row_hash="b" * 64,
            transform_version=run.transform_version,
            target_model_label="accounts.profile",
            target_pk=target_pk,
            state="migrated",
            reconciliation_status="pending",
            approved_issue_id=issue.pk,
            reviewed_by_id=issue.reviewed_by_id,
            reviewed_at=issue.reviewed_at,
            review_reason_code=issue.review_reason_code,
            review_evidence_digest=issue.review_evidence_digest,
            applied_by_id=actor.pk,
        )
        self._old_model("LegacyEntityObservation").objects.create(
            organization_id=issue.organization_id,
            run_id=run.pk,
            entity_map_id=entity_map.pk,
            map_version_id=version.pk,
            source_row_hash="b" * 64,
            transform_version=run.transform_version,
            target_model_label="accounts.profile",
            target_pk=target_pk,
            state="migrated",
            reconciliation_status="pending",
        )
        return version

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
        run = self._create_running_run(organization=organization, actor=actor)
        entity_map, _version, observation = self._create_migrated_entity_map(run=run, organization=organization)
        observation_id = observation.pk
        self.assertEqual(LegacyEntityMapVersion.objects.filter(entity_map_id=entity_map.pk).count(), 1)

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

        first_run = self._create_running_run(organization=organization, actor=actor, transform_version="transform-v1")
        entity_map, initial_version, _observation = self._create_migrated_entity_map(
            run=first_run, organization=organization
        )
        second_run = self._create_running_run(organization=organization, actor=actor, transform_version="transform-v2")
        issue = self._create_open_issue(
            run=second_run,
            organization=organization,
            rule_code="legacy_entity_identity_conflict",
            severity="error",
            payload_digest="c" * 64,
            entity_map_id=entity_map.pk,
        )
        issue = self._review_issue(
            issue,
            actor=actor,
            decision="resolved",
            reason_code="approved-remap",
            evidence_digest="d" * 64,
        )
        self._apply_reviewed_remap(
            issue=issue,
            run=second_run,
            entity_map=entity_map,
            predecessor=initial_version,
            actor=actor,
            target_pk="43",
        )
        self.assertEqual(LegacyEntityMapVersion.objects.filter(entity_map_id=entity_map.pk).count(), 2)

        with self.assertRaisesRegex(RuntimeError, "reverse_blocked_by_review_history"):
            MigrationExecutor(connection).migrate([self.migrate_to])

        self.assertEqual(LegacyEntityMapVersion.objects.filter(entity_map_id=entity_map.pk).count(), 2)
        self.assertEqual(LegacyEntityObservation.objects.filter(entity_map_id=entity_map.pk).count(), 2)
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
        initial = LegacyEntityMapVersion.objects.get(entity_map_id=entity_map.pk, version_number=1)
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
        run = self._create_running_run(organization=organization, actor=actor, source_row_count=0)
        issue = self._create_open_issue(
            run=run,
            organization=organization,
            rule_code="manual-review",
            severity="warning",
            payload_digest="b" * 64,
        )
        issue = self._review_issue(
            issue,
            actor=actor,
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
