"""Private fixed-scope collector: actual migrated PostgreSQL, both readonly RLS modes."""

import json
from unittest.mock import patch

from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase, override_settings

from apps.audit.models import AuditLog
from apps.registrar.models import Enrollment, LessonMark
from apps.workload.services.scoped_snapshot import four_cell_history as probe
from apps.workload.tests.factories import make_org
from apps.workload.tests.test_chair_cells_export import ChairCellsExportTests as Fixture
from core.rls import apply_rls_request_context


class FourCellHistoryPostgresTests(TransactionTestCase):
    setUp_base = Fixture.setUp
    new_offering = Fixture.new_offering

    def setUp(self):
        self.setUp_base()
        self.student.profile.organization = self.org
        self.student.profile.save(update_fields=["organization"])
        self.case = {
            5458056: {
                "student_id": self.student.pk,
                "enrollment_id": str(self.enrollment.pk),
                "offering_id": str(self.offering.pk),
                "lesson_id": str(self.lesson.pk),
                "date": "2026-10-20",
                "kind": "seminar",
                "start_time": "13:35:00",
            }
        }
        self.pin = patch.dict(probe.CASES, self.case, clear=True)
        self.pin.start()
        self.addCleanup(self.pin.stop)
        self.audit = AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type="registrar.grade.full-edit",
            resource_id=str(self.offering.pk),
            changes=[
                {
                    "enrollment_id": str(self.enrollment.pk),
                    "lesson_id": str(self.lesson.pk),
                    "old": "q/b",
                    "new": "—",
                }
            ],
            old_values={"password": "PRIVATE_DO_NOT_EXPORT"},
            new_values={"email": "PRIVATE_CONTACT"},
            reason="PRIVATE_REASON",
        )

    def read(self, mode=False):
        with override_settings(RLS_TRANSACTION_SCOPED=mode):
            with transaction.atomic():
                with connection.cursor() as c:
                    c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    c.execute("SET LOCAL statement_timeout='30s'")
                apply_rls_request_context(user_id=self.actor.pk, org_id=self.org.pk, bypass=False, local=True)
                result = probe.collect_four_cell_history()
                with connection.cursor() as c:
                    c.execute("SHOW transaction_read_only")
                    self.assertEqual(c.fetchone()[0], "on")
                return result

    def fingerprint(self):
        return json.dumps(
            {
                "marks": list(LessonMark.objects.values()),
                "enrollments": list(Enrollment.objects.values()),
                "audits": list(AuditLog.objects.values()),
            },
            cls=DjangoJSONEncoder,
            sort_keys=True,
        )

    def test_actual_readonly_both_rls_modes_privacy_and_raw_unchanged(self):
        before = self.fingerprint()
        for mode in [False, True]:
            with self.subTest(mode=mode):
                result = self.read(mode)
                self.assertEqual(len(result["four_cell_history_audits"]), 1)
                self.assertTrue(result["four_cell_history_changes"][0]["clear_evidence"])
                self.assertFalse(result["four_cell_history_scope"][0]["automatic_apply_authority"])
                self.assertTrue(result["four_cell_history_scope"][0]["audit_is_best_effort"])
                raw = json.dumps(result, cls=DjangoJSONEncoder)
                self.assertNotIn("PRIVATE", raw)
                self.assertNotIn("password", raw)
        self.assertEqual(before, self.fingerprint())

    def test_foreign_tenant_same_resource_key_and_unrelated_rows_never_exported(self):
        other = make_org("history-foreign")
        AuditLog.objects.create(
            organization=other,
            user=self.actor,
            action="update",
            resource_type="registrar.grade.full-edit",
            resource_id=str(self.offering.pk),
            changes=self.audit.changes,
        )
        AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="delete",
            resource_type="unknown",
            resource_id="unrelated",
            changes=[],
        )
        self.assertEqual(
            [r["id"] for r in self.read()["four_cell_history_audits"]],
            [str(self.audit.pk)],
        )

    def test_actual_write_on_read_blocked_and_rolled_back(self):
        before = AuditLog.objects.count()

        def bad(row, labels):
            AuditLog.objects.create(
                organization=self.org,
                user=self.actor,
                action="update",
                resource_type="BAD",
                resource_id="BAD",
            )

        with patch.object(probe, "project_audit", side_effect=bad):
            with self.assertRaises(DatabaseError):
                self.read()
        self.assertEqual(before, AuditLog.objects.count())

    def test_row_byte_limits_and_normal_write_transaction_rejected(self):
        with patch.object(probe, "MAX_ROWS", 0):
            with self.assertRaisesRegex(ValueError, "row_budget"):
                self.read()
        with patch.object(probe, "MAX_AUDIT_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "byte_budget"):
                self.read()
        with transaction.atomic():
            with self.assertRaisesRegex(ValueError, "readonly_pg_required"):
                probe.collect_four_cell_history()


del Fixture
