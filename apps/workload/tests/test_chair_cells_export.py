"""Real migrated PostgreSQL audit export: complete history, tenant isolation, no writes."""

import hashlib
import importlib.util
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.organizations.models import Organization
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.workload.services.chair_cells_export import capture, save_encrypted
from apps.workload.services.chair_cells_export.collect import SCHEMAS, collect
from apps.workload.services.chair_cells_export.spec import PERIOD, batch_spec
from apps.workload.services.scoped_snapshot import SnapshotError
from apps.workload.services.scoped_snapshot.data import ORG
from apps.workload.tests.factories import activate_member, make_org, make_structure

ROOT = Path(__file__).resolve().parents[3]
User = get_user_model()


class ChairCellsExportTests(TransactionTestCase):
    def setUp(self):
        self.actor = User.objects.create_superuser("cell_audit_operator", password="AUTH_SECRET_SENTINEL")
        self.org = Organization.objects.create(
            id=ORG,
            name="Audit",
            slug="audit-cells",
            owner=self.actor,
            org_type="university",
            status="active",
            is_active=True,
        )
        self.stack = make_structure(self.org, code="CELLS")
        self.stack["period"].id = PERIOD
        self.stack["period"].name = "Fixed audit fall"
        self.stack["period"].save(force_insert=True)
        self.student = User.objects.create_user("STUDENT_PIN_CONTACT_SENTINEL")
        activate_member(self.org, self.student, "cell_student", permissions=["course.view"])
        self.offering = self.new_offering(self.stack)
        self.enrollment = Enrollment.objects.create(organization=self.org, offering=self.offering, student=self.student)
        self.lesson = Lesson.objects.create(
            organization=self.org, offering=self.offering, date="2026-10-20", kind="seminar", created_by=self.actor
        )
        self.mark = LessonMark.objects.create(
            organization=self.org,
            lesson=self.lesson,
            enrollment=self.enrollment,
            score=7,
            status="excused",
            entered_by=self.actor,
        )
        self.spec = {"offerings": [{"id": str(self.offering.id), "chair_id": None, "classification": "unassigned"}]}
        self.pin = patch("apps.workload.services.chair_cells_export.batch_spec", return_value=self.spec)
        self.pin.start()
        self.addCleanup(self.pin.stop)

    def new_offering(self, stack, **kwargs):
        return CourseOffering.objects.create(
            organization_id=stack["subject"].organization_id,
            subject=stack["subject"],
            period=stack["period"],
            group=stack["group"],
            **kwargs,
        )

    def test_registry_all_1791_exact_ids_once_no_arbitrary_ids(self):
        path = ROOT / "apps/workload/services/chair_cells_export/batches.json"
        registry = json.loads(path.read_text())
        ids = [r["id"] for b in registry["batches"].values() for r in b["offerings"]]
        self.assertEqual(len(ids), 1791)
        self.assertEqual(len(set(ids)), 1791)
        self.assertTrue(all(len(b["offerings"]) <= 25 for b in registry["batches"].values()))
        self.assertEqual(batch_spec("chair-cells-001"), registry["batches"]["chair-cells-001"])
        with self.assertRaisesRegex(SnapshotError, "pinned_batch"):
            batch_spec(str(self.offering.id))

    def test_ilahe_history_seeds_split_without_global_partition_loss(self):
        selected = batch_spec("chair-cells-070")["offerings"]
        residual = batch_spec("chair-cells-091")["offerings"]
        self.assertEqual(
            {row["id"] for row in selected},
            {
                "caad2073-173d-48e1-89fd-3c4405c4b87d",
                "f1882bc7-c5d0-43ac-ba3f-7ce8c30f4e76",
            },
        )
        self.assertEqual(len(residual), 18)
        self.assertFalse({row["id"] for row in selected} & {row["id"] for row in residual})

    def test_schema_exact_history_ids_timestamps_and_no_auth_data(self):
        before = list(LessonMark.objects.values())
        result = capture(self.actor.username, "chair-cells-001")
        for name, fields in SCHEMAS.items():
            for row in result["data"][name]:
                self.assertEqual(set(row), set(fields))
        mark = result["data"]["marks"][0]
        self.assertEqual(
            (mark["id"], mark["entered_by_id"], mark["score"], mark["status"]),
            (self.mark.id, self.actor.id, 7, "excused"),
        )
        self.assertEqual(mark["created_at"], self.mark.created_at)
        self.assertEqual(before, list(LessonMark.objects.values()))
        encoded = json.dumps(result, default=str)
        for sentinel in (self.student.username, "AUTH_SECRET_SENTINEL", '"password"', '"email"', '"payload"'):
            self.assertNotIn(sentinel, encoded)

    def test_auth_queries_select_only_actor_identity_and_never_credentials(self):
        def deny_sensitive(execute, sql, params, many, context):
            if 'FROM "auth_user"' in sql:
                columns = sql.split(" FROM ", 1)[0]
                for name in ("password", "email", "first_name", "last_name", "username"):
                    self.assertNotIn(f'"{name}"', columns)
            return execute(sql, params, many, context)

        with connection.execute_wrapper(deny_sensitive):
            capture(self.actor.username, "chair-cells-001")

    def test_mark_and_total_row_budgets_reject_instead_of_truncating(self):
        with patch("apps.workload.services.chair_cells_export.collect.MAX_MARKS", 0):
            with self.assertRaisesRegex(SnapshotError, "row_budget"):
                capture(self.actor.username, "chair-cells-001")
        with patch("apps.workload.services.chair_cells_export.collect.MAX_ROWS", 1):
            with self.assertRaisesRegex(SnapshotError, "total_row_budget"):
                capture(self.actor.username, "chair-cells-001")

    def test_typed_source_ledger_only_selected_identity_no_payload(self):
        run_model = apps.get_model("legacy_import", "LegacyMigrationRun")
        ledger_model = apps.get_model("legacy_import", "LegacyEntityMap")
        run = run_model.objects.create(
            organization=self.org,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            schema_version="v1",
            transform_version="v1",
            mode="profile",
        )

        run_model.objects.filter(pk=run.id).update(status="running", started_at=timezone.now())

        def mapping(key, label, target):
            return ledger_model.objects.create(
                organization=self.org,
                source_system="myedu_mariadb",
                entity_type="student",
                legacy_pk=key,
                source_row_hash="b" * 64,
                transform_version="v1",
                target_model_label=label,
                target_pk=str(target),
                created_run=run,
                state="migrated",
            )

        wanted = mapping("123456", "auth.user", self.student.id)
        course_key = mapping("rooBx39tsK:2", "registrar.courseoffering", self.offering.id)
        mapping("789", "auth.user", User.objects.create_user("UNRELATED_PRIVATE").id)
        rows = capture(self.actor.username, "chair-cells-001")["data"]["ledger"]
        self.assertEqual({r["id"] for r in rows}, {wanted.id, course_key.id})
        with patch("apps.workload.services.chair_cells_export.collect.re.fullmatch", return_value=None):
            with self.assertRaisesRegex(SnapshotError, "key_schema_unsafe"):
                capture(self.actor.username, "chair-cells-001")

    def test_wall_time_budget_prevents_unbounded_collector(self):
        with patch("apps.workload.services.chair_cells_export.monotonic", side_effect=[0, 121]):
            with self.assertRaisesRegex(SnapshotError, "time_budget"):
                capture(self.actor.username, "chair-cells-001")

    def test_dropped_predecessor_offering_and_marks_are_exported(self):
        other = make_structure(self.org, code="PAST")
        other["period"] = self.stack["period"]
        other["subject"] = self.stack["subject"]
        previous = self.new_offering(other, is_active=False)
        old = Enrollment.objects.create(
            organization=self.org,
            offering=previous,
            student=self.student,
            status="dropped",
            superseded_by=self.enrollment,
        )
        lesson = Lesson.objects.create(organization=self.org, offering=previous, date="2026-09-20")
        mark = LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=old, status="absent")
        result = capture(self.actor.username, "chair-cells-001")["data"]
        self.assertEqual({r["id"] for r in result["offerings"]}, {previous.id, self.offering.id})
        self.assertIn(mark.id, {r["id"] for r in result["marks"]})
        self.assertEqual(
            next(r for r in result["enrollments"] if r["id"] == old.id)["superseded_by_id"], self.enrollment.id
        )

    def test_history_scope_and_size_fail_closed(self):
        other = make_structure(self.org, code="PAST")
        previous = self.new_offering(other)
        self.spec["offerings"][0]["id"] = str(previous.id)
        with self.assertRaisesRegex(SnapshotError, "scope_changed"):
            capture(self.actor.username, "chair-cells-001")
        self.spec["offerings"][0]["id"] = str(self.offering.id)
        previous.period = self.stack["period"]
        previous.subject = self.stack["subject"]
        previous.save(update_fields=["period", "subject"])
        Enrollment.objects.create(
            organization=self.org,
            offering=previous,
            student=self.student,
            status="dropped",
            superseded_by=self.enrollment,
        )
        with patch("apps.workload.services.chair_cells_export.collect.MAX_OFFERINGS", 1):
            with self.assertRaisesRegex(SnapshotError, "history_course_budget"):
                capture(self.actor.username, "chair-cells-001")

    def test_real_readonly_transaction_rejects_write(self):
        def bad(_spec):
            LessonMark.objects.filter(id=self.mark.id).update(score=1)

        with patch("apps.workload.services.chair_cells_export.collect", side_effect=bad):
            with self.assertRaises(Exception) as raised:
                capture(self.actor.username, "chair-cells-001")
        self.assertIn("read-only", str(raised.exception))
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.score, 7)
        with transaction.atomic(), self.assertRaisesRegex(SnapshotError, "fresh_postgresql"):
            capture(self.actor.username, "chair-cells-001")

    def test_actor_scope_and_foreign_batch_refused(self):
        foreign = make_org("foreign-cells")
        stack = make_structure(foreign, code="FOREIGN")
        offering = self.new_offering(stack)
        self.spec["offerings"][0]["id"] = str(offering.id)
        with self.assertRaisesRegex(SnapshotError, "scope_changed"):
            capture(self.actor.username, "chair-cells-001")
        outsider = User.objects.create_superuser("outside_operator", password="secret")
        with self.assertRaisesRegex(SnapshotError, "fixed_tenant_superuser"):
            capture(outsider.username, "chair-cells-001")
        with self.assertRaisesRegex(SnapshotError, "fixed_tenant_superuser"):
            capture(self.student.username, "chair-cells-001")

    def test_force_rls_no_bypass_in_both_pooling_modes(self):
        foreign = make_org("foreign-rls-cells")
        stack = make_structure(foreign, code="FOREIGN_RLS")
        foreign_offering = self.new_offering(stack)

        def restricted(spec):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE rls_app_role")
                cursor.execute("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname=current_user")
                self.assertEqual(cursor.fetchone(), (False, False))
                cursor.execute("SHOW transaction_read_only")
                self.assertEqual(cursor.fetchone()[0], "on")
            self.assertFalse(CourseOffering.objects.filter(pk=foreign_offering.id).exists())
            return collect(spec)

        for scoped in (False, True):
            with (
                override_settings(RLS_TRANSACTION_SCOPED=scoped),
                patch("apps.workload.services.chair_cells_export.collect", side_effect=restricted),
            ):
                self.assertEqual(capture(self.actor.username, "chair-cells-001")["counts"]["marks"], 1)

    def test_correction_reversal_and_hygiene_no_notes_names_urls_or_json(self):
        import uuid

        correction_model = apps.get_model("registrar", "JournalCorrection")
        correction = correction_model.objects.create(
            organization=self.org,
            lesson_mark=self.mark,
            lesson_mark_ref=self.mark.id,
            lesson_ref=self.lesson.id,
            enrollment_ref=self.enrollment.id,
            field="score",
            old_score=3,
            new_score=7,
            reason="technical",
            note="PRIVATE_NOTE_SENTINEL",
            document="https://PRIVATE_URL_SENTINEL/file.pdf",
            corrected_by=self.actor,
            corrected_by_name="PRIVATE_NAME_SENTINEL",
        )
        reversal = apps.get_model("registrar", "CorrectionReversal").objects.create(
            organization=self.org,
            journal_correction=correction,
            reverted_by=self.actor,
            reverted_by_ref=str(self.actor.id),
            reason_note="PRIVATE_REVERSAL_SENTINEL",
        )
        hygiene = apps.get_model("registrar", "JournalHygieneDecision").objects.create(
            organization=self.org,
            enrollment=self.enrollment,
            batch=uuid.uuid4(),
            category="empty_subject",
            reason_code="PRIVATE_CODE_SENTINEL",
            from_status="enrolled",
            to_status="dropped",
            evidence={"secret": "PRIVATE_JSON_SENTINEL"},
            evidence_digest="a" * 64,
            reason="PRIVATE_HYGIENE_SENTINEL",
            decided_by=self.actor,
            decided_by_name="PRIVATE_NAME_SENTINEL",
        )
        snapshot = capture(self.actor.username, "chair-cells-001")
        data = snapshot["data"]
        self.assertEqual(data["journal_corrections"][0]["id"], correction.id)
        self.assertEqual(data["journal_corrections"][0]["old_score"], 3)
        self.assertEqual(data["correction_reversals"][0]["id"], reversal.id)
        self.assertTrue(data["correction_reversals"][0]["note_present"])
        self.assertEqual(data["hygiene_decisions"][0]["id"], hygiene.id)
        self.assertEqual(data["hygiene_decisions"][0]["reason_code"], "unknown")
        self.assertFalse(data["hygiene_decisions"][0]["reason_code_known"])
        self.assertNotIn("PRIVATE_", json.dumps(snapshot, default=str))
        self.assertTrue(snapshot["correction_coverage"]["override_proof_complete"])
        apps.get_model("registrar", "LessonCorrection").objects.create(
            organization=self.org,
            lesson=None,
            is_deletion=True,
            lesson_label="PRIVATE_DELETED_LABEL",
            reason="technical",
            note="PRIVATE_NOTE_SENTINEL",
            document="PRIVATE_URL_SENTINEL",
            corrected_by=self.actor,
            corrected_by_name="PRIVATE_NAME_SENTINEL",
        )
        snapshot = capture(self.actor.username, "chair-cells-001")
        self.assertFalse(snapshot["correction_coverage"]["override_proof_complete"])
        self.assertEqual(
            snapshot["correction_coverage"]["coverage_gaps"]["tenant_deleted_lesson_corrections_unlocatable"], 1
        )
        self.assertNotIn("PRIVATE_", json.dumps(snapshot, default=str))

    def test_crypto_roundtrip_tamper_size_and_private_output(self):
        module_spec = importlib.util.spec_from_file_location(
            "decrypt_cells_test", ROOT / "scripts/ops/decrypt_workload_snapshot.py"
        )
        decrypt = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(decrypt)
        private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        public = private.public_key()
        pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        fingerprint = hashlib.sha256(der).hexdigest()
        secret = private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        snapshot = capture(self.actor.username, "chair-cells-001")
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("apps.workload.services.scoped_snapshot.KEY_FINGERPRINT", fingerprint),
            patch.object(decrypt, "KEY_FINGERPRINT", fingerprint),
        ):
            key, output = Path(tmp) / "key.pem", Path(tmp) / "snapshot.enc.json"
            key.write_bytes(pem)
            save_encrypted(snapshot, key, output)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(str(self.mark.id).encode(), output.read_bytes())
            restored = decrypt.decrypt_snapshot(output.read_bytes(), secret)
            self.assertEqual(restored["data"]["marks"][0]["id"], str(self.mark.id))
            plaintext = decrypt.write_new_snapshot(restored, tmp)
            self.assertTrue(plaintext.name.startswith("wcu-journal-cells-"))
            self.assertEqual(plaintext.stat().st_mode & 0o777, 0o600)
            restored["data"]["marks"][0]["note"] = "PRIVATE_FORBIDDEN_FIELD"
            restored["schema_fields"]["marks"].append("note")
            forbidden = Path(tmp) / "forbidden.enc.json"
            save_encrypted(restored, key, forbidden)
            with self.assertRaisesRegex(ValueError, "schema_invalid"):
                decrypt.decrypt_snapshot(forbidden.read_bytes(), secret)

            with self.assertRaises(FileExistsError):
                save_encrypted(snapshot, key, output)
            broken = json.loads(output.read_bytes())
            broken["ciphertext"] = ("A" if broken["ciphertext"][0] != "A" else "B") + broken["ciphertext"][1:]
            with self.assertRaises(InvalidTag):
                decrypt.decrypt_snapshot(json.dumps(broken).encode(), secret)
            with patch("apps.workload.services.chair_cells_export.MAX_BYTES", 100):
                with self.assertRaisesRegex(SnapshotError, "size_budget"):
                    save_encrypted(snapshot, key, Path(tmp) / "too-large")
            self.assertFalse((Path(tmp) / "too-large").exists())

    def test_command_logs_only_numeric_counts_and_ciphertext_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "cells.enc.json"
            log = StringIO()
            call_command(
                "export_wcu_journal_cells",
                actor=self.actor.username,
                batch="chair-cells-001",
                public_key=str(ROOT / "scripts/data/wcu_workload_export_public.pem"),
                output=str(output),
                stdout=log,
            )
            self.assertRegex(log.getvalue(), r"^encrypted_sha256=[a-f0-9]{64} offerings=1 marks=1\n$")
            with self.assertRaisesMessage(CommandError, "journal_cells_export_refused"):
                call_command(
                    "export_wcu_journal_cells",
                    actor=self.actor.username,
                    batch="chair-cells-001",
                    public_key="PRIVATE_PATH_SENTINEL",
                    output=str(output),
                    stdout=log,
                )
            self.assertNotIn("PRIVATE_PATH_SENTINEL", log.getvalue())

    def test_command_suppresses_unexpected_exception_values(self):
        with patch(
            "apps.workload.management.commands.export_wcu_journal_cells.capture",
            side_effect=RuntimeError("PRIVATE_ERROR_SENTINEL"),
        ):
            with self.assertRaises(CommandError) as raised:
                call_command(
                    "export_wcu_journal_cells",
                    actor=self.actor.username,
                    batch="chair-cells-001",
                    public_key="PRIVATE_PATH",
                    output="PRIVATE_OUTPUT",
                )
        self.assertEqual(str(raised.exception), "journal_cells_export_refused")
        self.assertTrue(raised.exception.__suppress_context__)
