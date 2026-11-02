"""Real PostgreSQL proof for the exact fresh-readonly worker exemption."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TransactionTestCase, override_settings

from psycopg2.errors import ReadOnlySqlTransaction

from apps.audit.models import AuditLog
from apps.organizations.models import Organization
from apps.workload.services import source58_audit_diagnostic as export
from apps.workload.services.scoped_snapshot import SnapshotError
from apps.workload.services.scoped_snapshot.source58_evidence_spec import HISTORY_SCOPE, ORG


class Source58AuditCapturePostgresTests(TransactionTestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_superuser("source58_operator", password="test-only")
        self.org = Organization.objects.create(
            id=ORG,
            name="Fixed Source58",
            slug="fixed-source58",
            owner=self.actor,
            org_type="university",
            status="active",
            is_active=True,
        )
        self.case = next(iter(HISTORY_SCOPE.cases.values()))
        self.audit = AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type="registrar.grade.full-edit",
            resource_id=self.case["offering_id"],
            changes={"lesson_id": self.case["lesson_id"], "old": "q/b", "new": None},
            reason="PRIVATE_CLEAR_INTENT_RETAINED",
        )

    def test_outer_atomic_rejected_before_scope_or_output(self):
        with transaction.atomic(), patch.object(export, "reference_ids") as scope:
            with self.assertRaisesMessage(SnapshotError, "fresh_postgresql_transaction_required"):
                export.capture(self.actor.username, "not-read", "not-written")
        scope.assert_not_called()

    def test_real_db_rejects_write_and_preserves_full_scope_identity_both_rls_modes(self):
        original = list(AuditLog.objects.filter(pk=self.audit.pk).values())
        for scoped in (False, True):
            with self.subTest(transaction_scoped=scoped), override_settings(RLS_TRANSACTION_SCOPED=scoped):
                captured = []

                def consume(rows, public_key, output, context, captured=captured):
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT current_setting('transaction_read_only'), "
                            "current_setting('transaction_isolation'), "
                            "current_setting('app.current_org_id'), "
                            "current_setting('app.current_user_id'), "
                            "current_setting('app.bypass_rls', true)"
                        )
                        readonly, isolation, org, user, bypass = cursor.fetchone()
                    self.assertEqual(
                        (readonly, isolation, org, user), ("on", "repeatable read", ORG, str(self.actor.pk))
                    )
                    self.assertNotEqual(bypass, "on")
                    # A real write, not a mocked assertion, must be refused by PostgreSQL.
                    # Bypass only the Python SELECT-only wrapper so PostgreSQL itself
                    # receives the forbidden UPDATE; the native transaction stays intact.
                    table = connection.ops.quote_name(AuditLog._meta.db_table)
                    with connection.connection.cursor() as cursor:
                        cursor.execute("SAVEPOINT source58_write_probe")
                        try:
                            with self.assertRaises(ReadOnlySqlTransaction) as error:
                                cursor.execute(
                                    f"UPDATE {table} SET reason=%s WHERE id=%s", ["MUST_NOT_WRITE", str(self.audit.pk)]
                                )
                            self.assertEqual(error.exception.pgcode, "25006")
                        finally:
                            cursor.execute("ROLLBACK TO SAVEPOINT source58_write_probe")
                            cursor.execute("RELEASE SAVEPOINT source58_write_probe")
                    captured.extend(rows)
                    self.assertEqual([row[0] for row in captured], [str(self.audit.pk)])
                    self.assertIn(b"PRIVATE_CLEAR_INTENT_RETAINED", captured[0][1])
                    self.assertIn(b'"new": null', captured[0][1])
                    self.assertEqual(context["organization_id"], ORG)
                    self.assertEqual(context["matched_audit_count"], 1)
                    self.assertEqual(context["clear_delete_intent"], "UNREVIEWED_FULL_CONTENT")
                    self.assertTrue(context["unlocatable_history_remains_hold"])
                    return "a" * 64

                with (
                    TemporaryDirectory() as folder,
                    patch.object(export, "reference_ids", return_value={self.case["offering_id"]}),
                    patch.object(export, "write_bundle", side_effect=consume),
                ):
                    self.assertEqual(export.capture(self.actor.username, "public", str(Path(folder) / "out")), "a" * 64)
                self.assertEqual(list(AuditLog.objects.filter(pk=self.audit.pk).values()), original)

    def test_unrelated_superuser_rejected_without_reading_source_scope(self):
        other = get_user_model().objects.create_superuser("unrelated_source58", password="test-only")
        with patch.object(export, "reference_ids") as scope:
            with self.assertRaisesMessage(ValueError, "fixed_four_actor_tenant_required"):
                export.capture(other.username, "not-read", "not-written")
        scope.assert_not_called()
