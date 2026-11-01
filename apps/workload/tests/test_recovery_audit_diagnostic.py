"""Real PG metadata-only diagnostics keep oversized audit JSON private and unchanged."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase, override_settings

from apps.audit.models import AuditLog
from apps.workload.services import recovery_audit_diagnostic as diagnostic
from apps.workload.services.scoped_snapshot import four_cell_history as strict
from apps.workload.tests import test_chair_cells_export as fixtures
from apps.workload.tests.factories import make_org
from core.rls import apply_rls_request_context


class RecoveryAuditDiagnosticTests(TransactionTestCase):
    setUp_base = fixtures.ChairCellsExportTests.setUp
    new_offering = fixtures.ChairCellsExportTests.new_offering

    def setUp(self):
        self.setUp_base()
        self.cases = {
            1: {
                "student_id": self.student.pk,
                "enrollment_id": str(self.enrollment.pk),
                "offering_id": str(self.offering.pk),
                "lesson_id": str(self.lesson.pk),
                "date": "2026-10-20",
                "kind": "seminar",
                "start_time": "13:35:00",
            }
        }
        self.case_pin = patch.dict(diagnostic.CASES, self.cases, clear=True)
        self.case_pin.start()
        self.addCleanup(self.case_pin.stop)
        self.source_pin = patch.object(diagnostic, "history_scope", return_value=SimpleNamespace(cases=self.cases))
        self.source_pin.start()
        self.addCleanup(self.source_pin.stop)
        self.audit = AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type="registrar.grade.full-edit",
            resource_id=str(self.offering.pk),
            reason="PRIVATE_REASON",
            old_values={"password": "PRIVATE_SECRET_" + "x" * (1024 * 1024)},
            changes=[
                {"enrollment_id": str(self.enrollment.pk), "lesson_id": str(self.lesson.pk), "old": "q/b", "new": "—"}
            ],
        )

    def capture(self):
        return diagnostic.capture(self.actor.username)

    def test_oversized_row_is_hashed_not_fetched_and_strict_guard_still_rejects_both_rls(self):
        before = list(AuditLog.objects.filter(pk=self.audit.pk).values())
        for mode in (False, True):
            with self.subTest(mode=mode), override_settings(RLS_TRANSACTION_SCOPED=mode):
                payload = self.capture()
                self.assertFalse(payload["eligible_for_apply"])
                self.assertFalse(payload["absence_claim"])
                self.assertFalse(payload["raw_body_included"])
                for scope in payload["data"].values():
                    self.assertEqual(scope["row_count"], 1)
                    self.assertGreater(scope["rows"][0]["old_values_bytes"], 1024 * 1024)
                    self.assertRegex(scope["rows"][0]["old_values_sha"], r"^[a-f0-9]{64}$")
                    self.assertFalse(scope["raw_json_fetched"])
                    self.assertFalse(scope["history_cleared_for_apply"])
                raw = json.dumps(payload, cls=DjangoJSONEncoder)
                self.assertNotIn("PRIVATE", raw)
                self.assertNotIn("password", raw)
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    apply_rls_request_context(user_id=self.actor.pk, org_id=self.org.pk, bypass=False, local=True)
                    with self.assertRaisesRegex(ValueError, "four_cell_audit_byte_budget_exceeded"):
                        strict.collect_four_cell_history()
        self.assertEqual(before, list(AuditLog.objects.filter(pk=self.audit.pk).values()))

    def test_other_tenant_and_unrelated_same_tenant_rows_are_not_exposed(self):
        other = make_org("audit-diagnostic-other")
        AuditLog.objects.create(organization=other, action="delete", resource_id=str(self.offering.pk))
        AuditLog.objects.create(organization=self.org, action="delete", resource_id="unrelated")
        payload = self.capture()
        self.assertEqual([str(self.audit.pk)], [r["id"] for r in payload["data"]["four"]["rows"]])

    def test_non_superuser_inactive_actor_and_wrong_tenant_are_rejected(self):
        for field in ("is_active", "is_superuser"):
            type(self.actor).objects.filter(pk=self.actor.pk).update(**{field: False})
            with self.assertRaises((ObjectDoesNotExist, ValueError)):
                self.capture()
            type(self.actor).objects.filter(pk=self.actor.pk).update(**{field: True})

    def test_collector_is_actually_readonly(self):
        original = diagnostic.metadata

        def attempt(cases):
            AuditLog.objects.filter(pk=self.audit.pk).update(action="delete")
            return original(cases)

        with patch.object(diagnostic, "metadata", side_effect=attempt), self.assertRaises(DatabaseError):
            self.capture()
        self.audit.refresh_from_db()
        self.assertEqual(self.audit.action, "update")
