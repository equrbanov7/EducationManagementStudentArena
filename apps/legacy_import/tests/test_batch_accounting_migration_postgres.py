"""PostgreSQL migration and concurrency checks for batch accounting."""

import threading
from concurrent.futures import ThreadPoolExecutor

from django.contrib.auth import get_user_model
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase

import pytest

from apps.legacy_import.models import LegacyImportBatch, LegacyMigrationRun
from apps.legacy_import.services.batch_accounting import record_batch
from apps.legacy_import.services.ledger import LegacyLedgerBusyError, create_run, start_run
from apps.organizations.models import Organization
from core.constants import OrganizationType

pytestmark = [pytest.mark.postgres, pytest.mark.migration_roundtrip]
User = get_user_model()


def _allow(**_kwargs):
    return True


@pytest.mark.skipif(connection.vendor != "postgresql", reason="Batch migration checks require PostgreSQL")
class BatchAccountingMigrationTests(TransactionTestCase):
    migrate_from = ("legacy_import", "0006_scalable_batch_accounting")
    migrate_to = ("legacy_import", "0005_reviewed_mapping_versions")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        self.latest_targets = executor.loader.graph.leaf_nodes()
        executor.migrate([self.migrate_from])

    def _fixture_teardown(self):
        # Append-only triggers deliberately block Django's normal TRUNCATE flush.
        MigrationExecutor(connection).migrate(self.latest_targets)
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE legacy_import_legacyimportbatch DISABLE TRIGGER USER")
            cursor.execute("ALTER TABLE legacy_import_legacymigrationrun DISABLE TRIGGER USER")
            cursor.execute("DELETE FROM legacy_import_legacyimportbatch")
            cursor.execute("DELETE FROM legacy_import_legacymigrationrun")
            cursor.execute("ALTER TABLE legacy_import_legacyimportbatch ENABLE TRIGGER USER")
            cursor.execute("ALTER TABLE legacy_import_legacymigrationrun ENABLE TRIGGER USER")
        MigrationExecutor(connection).migrate([("legacy_import", "0001_initial")])
        super()._fixture_teardown()
        MigrationExecutor(connection).migrate(self.latest_targets)

    def _running_run(self, *, rows=2):
        actor = User.objects.create_user(
            username="batch_migration_actor",
            email="batch-migration-actor@example.test",
            password="test-only",
        )
        organization = Organization.objects.create(
            name="Batch Migration Organization",
            slug="batch-migration-organization",
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
            source_row_count=rows,
            schema_version="schema-v1",
            transform_version="transform-v1",
            mode=LegacyMigrationRun.Mode.REHEARSAL,
            accounting_mode=LegacyMigrationRun.AccountingMode.BATCH,
        )
        return start_run(run_id=run.pk, actor=actor, authorize=_allow), actor

    def _record(self, run, actor):
        return record_batch(
            run_id=run.pk,
            actor=actor,
            authorize=_allow,
            source_table="students",
            entity_type="student",
            sequence=1,
            first_legacy_pk=10,
            last_legacy_pk=11,
            migrated_count=1,
            skipped_count=0,
            quarantined_count=1,
            contract_fingerprint="b" * 64,
            source_digest="c" * 64,
            classification_digest="d" * 64,
            target_digest="a" * 64,
        )

    def test_no_data_reverse_and_reapply_restore_exact_schema(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.legacy_import_legacyimportbatch')")
            self.assertIsNone(cursor.fetchone()[0])
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND table_name = 'legacy_import_legacymigrationrun' "
                "AND column_name = 'accounting_mode'"
            )
            self.assertEqual(cursor.fetchone(), (0,))
            cursor.execute("SELECT pg_get_functiondef('public.legacy_import_run_identity_guard()'::regprocedure)")
            self.assertNotIn("accounting_mode", cursor.fetchone()[0])

        MigrationExecutor(connection).migrate([self.migrate_from])
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.legacy_import_legacyimportbatch')")
            self.assertEqual(cursor.fetchone(), ("legacy_import_legacyimportbatch",))
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE oid = 'public.legacy_import_legacyimportbatch'::regclass"
            )
            self.assertEqual(cursor.fetchone(), (True, True))
        self.assertTrue(
            MigrationRecorder(connection)
            .migration_qs.filter(app="legacy_import", name="0006_scalable_batch_accounting")
            .exists()
        )

    def test_reverse_stops_before_batch_evidence_is_destroyed(self):
        run, actor = self._running_run()
        batch = self._record(run, actor)

        with self.assertRaisesRegex(RuntimeError, "legacy_import_0006_reverse_stop:batch_evidence_exists"):
            MigrationExecutor(connection).migrate([self.migrate_to])

        self.assertTrue(LegacyImportBatch.objects.filter(pk=batch.pk).exists())
        self.assertTrue(
            MigrationRecorder(connection)
            .migration_qs.filter(app="legacy_import", name="0006_scalable_batch_accounting")
            .exists()
        )
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                LegacyImportBatch.objects.filter(pk=batch.pk).update(chain_digest="f" * 64)

    def test_concurrent_exact_retry_converges_to_one_batch(self):
        run, actor = self._running_run()
        start_barrier = threading.Barrier(2)
        committed = threading.Event()

        def worker():
            close_old_connections()
            saw_busy = False
            try:
                start_barrier.wait(timeout=10)
                try:
                    batch = self._record(run, actor)
                except LegacyLedgerBusyError:
                    saw_busy = True
                    if not committed.wait(timeout=10):
                        raise AssertionError("concurrent batch writer did not commit")
                    batch = self._record(run, actor)
                committed.set()
                return batch.pk, saw_busy
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: worker(), range(2)))

        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(LegacyImportBatch.objects.count(), 1)
