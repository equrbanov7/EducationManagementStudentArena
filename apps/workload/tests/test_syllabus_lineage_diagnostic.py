"""Real PG forensic read-only cycle closure; ordinary content export stays strict."""

import base64
import copy
import hashlib
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase, override_settings

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.syllabus.models import Syllabus, SyllabusVersion
from apps.workload.services import syllabus_lineage_diagnostic as diagnostic
from apps.workload.services import syllabus_lineage_spec as spec
from apps.workload.services.scoped_snapshot import SnapshotError
from apps.workload.services.syllabus_content_export import capture as normal_capture
from apps.workload.services.syllabus_content_export import save_encrypted
from apps.workload.tests import test_syllabus_content_export as fixture


class LineageDiagnosticTests(TransactionTestCase):
    new_offering = fixture.SyllabusContentExportTests.new_offering
    _setup_fixture = fixture.SyllabusContentExportTests._setup_fixture
    document = fixture.SyllabusContentExportTests.document
    private_key = None

    def setUp(self):
        fixture.SyllabusContentExportTests.setUp(self)
        self.selection_pin = patch.object(spec, "selection", return_value=self.spec)
        self.selection_pin.start()
        self.addCleanup(self.selection_pin.stop)

    def cycle(self):
        SyllabusVersion.objects.filter(pk=self.base_version.pk).update(source_version=self.approved)
        Syllabus.objects.filter(pk=self.base.pk).update(reused_from=self.document_syllabus)
        Syllabus.objects.filter(pk=self.document_syllabus.pk).update(reused_from=self.base)

    def capture(self):
        return diagnostic.capture(self.actor.username)

    def scope(self):
        module = fixture.load_script("syllabus_lineage_scope")
        module.contract.selection = lambda: self.spec
        return module

    def serialized(self):
        return json.loads(json.dumps(self.capture(), default=str))

    def test_exact_cycle_edges_no_sections_or_pii_and_no_pointer_or_mark_mutation(self):
        self.cycle()
        before = (
            list(Syllabus.objects.values()),
            list(SyllabusVersion.objects.values()),
            self.mark.__class__.objects.get(pk=self.mark.pk).score,
        )
        queries = []

        def observe(execute, sql, params, many, context):
            queries.append(sql.lower())
            return execute(sql, params, many, context)

        with connection.execute_wrapper(observe):
            result = self.serialized()
        self.scope().validate(result)
        self.assertEqual(result["counts"]["cycles"], 2)
        self.assertEqual({c["model"] for c in result["data"]["cycles"]}, {"syllabus", "version"})
        version_cycle = next(c for c in result["data"]["cycles"] if c["model"] == "version")
        self.assertEqual(set(version_cycle["node_ids"]), {str(self.approved.pk), str(self.base_version.pk)})
        self.assertFalse(any("syllabus_syllabussection" in sql for sql in queries))
        self.assertFalse(result["eligible_for_apply"])
        self.assertFalse(result["coverage"]["normal_content_export_usable"])
        encoded = json.dumps(result)
        for sentinel in (
            "PRIVATE_CONTACT",
            "MEANINGFUL_HISTORICAL_TEXT",
            "AUTHORED_TOPIC_SECRET",
            self.student.username,
            '"password"',
            '"decision_reason"',
        ):
            self.assertNotIn(sentinel, encoded)
        self.assertEqual(
            before,
            (
                list(Syllabus.objects.values()),
                list(SyllabusVersion.objects.values()),
                self.mark.__class__.objects.get(pk=self.mark.pk).score,
            ),
        )
        with self.assertRaisesRegex(SnapshotError, "syllabus_lineage_cycle"):
            normal_capture(self.actor.username, "chair-cells-027")

    def test_self_cycle_terminates_and_all_approved_fallback_ancestry_is_included(self):
        SyllabusVersion.objects.filter(pk=self.base_version.pk).update(source_version=self.base_version)
        older = SyllabusVersion.objects.create(
            organization=self.org, syllabus=self.document_syllabus, major=4, status="draft"
        )
        Syllabus.objects.filter(pk=self.document_syllabus.pk).update(current_version=older, approved_version=None)
        result = self.capture()
        self.assertEqual(
            result["data"]["cycles"],
            [dict(model="version", relation="source_version_id", node_ids=[str(self.base_version.pk)])],
        )
        self.assertIn(older.pk, {v["id"] for v in result["data"]["versions"]})
        self.assertEqual(self.scope().validate(json.loads(json.dumps(result, default=str)))["counts"]["versions"], 3)

    def test_actor_and_tenant_guards_and_fresh_transaction_requirement(self):
        foreign = get_user_model().objects.create_superuser("foreign_lineage_auditor")
        with self.assertRaisesRegex(SnapshotError, "active_fixed_tenant_superuser_required"):
            diagnostic.capture(foreign.username)
        foreign_doc = copy.copy(self.base)
        foreign_doc.organization_id = foreign.pk  # Deliberately contradictory resolver result; never read it.
        with patch.object(diagnostic, "syllabus_for_offering", return_value=foreign_doc):
            with self.assertRaisesRegex(SnapshotError, "syllabus_closure_tenant_mismatch"):
                self.capture()
        self.actor.is_active = False
        self.actor.save(update_fields=["is_active"])
        with self.assertRaisesRegex(SnapshotError, "active_fixed_tenant_superuser_required"):
            self.capture()
        with transaction.atomic(), self.assertRaisesRegex(SnapshotError, "fresh_postgresql_transaction_required"):
            self.capture()

    def test_actual_database_write_is_rejected_in_both_rls_modes(self):
        for mode in (False, True):
            with self.subTest(mode=mode), override_settings(RLS_TRANSACTION_SCOPED=mode):
                with patch.object(
                    diagnostic,
                    "collect",
                    side_effect=lambda selection: get_user_model().objects.create_user("MUST_NOT_WRITE"),
                ):
                    with self.assertRaises(DatabaseError):
                        self.capture()
                self.assertFalse(get_user_model().objects.filter(username="MUST_NOT_WRITE").exists())
                self.assertTrue(self.capture()["read_only"])

    def test_caps_fail_without_partial_or_truncated_output(self):
        with patch.object(spec, "MAX_VERSIONS", 1), self.assertRaises(SnapshotError):
            self.capture()
        with (
            patch.object(spec, "MAX_BYTES", 1),
            self.assertRaisesRegex(SnapshotError, "syllabus_output_byte_budget_exceeded"),
        ):
            self.capture()

    def test_strict_schema_rejects_raw_notes_missing_edges_cycles_or_other_batch(self):
        self.cycle()
        original = self.serialized()
        for change in ("note", "edge", "cycle", "batch", "eligible", "extraneous_course"):
            value = copy.deepcopy(original)
            if change == "note":
                value["data"]["versions"][0]["reason_note"] = "PRIVATE_FIN_CONTACT_URL"
            elif change == "edge":
                value["data"]["edges"].pop()
                value["counts"]["edges"] -= 1
            elif change == "cycle":
                value["data"]["cycles"] = []
                value["counts"]["cycles"] = 0
            elif change == "batch":
                value["batch"] = "chair-cells-028"
            elif change == "extraneous_course":
                row = dict(value["data"]["offerings"][0], id="00000000-0000-4000-8000-000000000001")
                value["data"]["offerings"].append(row)
                value["counts"]["offerings"] += 1
            else:
                value["eligible_for_apply"] = True
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "syllabus_lineage_scope_invalid"):
                self.scope().validate(value)

    def test_real_command_authenticated_roundtrip_and_normal_decoder_rejects_diagnostic(self):
        self.cycle()
        if type(self).private_key is None:
            type(self).private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        private = type(self).private_key
        public_bytes = private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private_bytes = private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        fingerprint = hashlib.sha256(
            private.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        ).hexdigest()
        decoder, normal = fixture.load_script("decrypt_syllabus_lineage"), fixture.load_script(
            "decrypt_syllabus_content"
        )
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("apps.workload.services.scoped_snapshot.KEY_FINGERPRINT", fingerprint),
        ):
            public, output = Path(folder) / "public.pem", Path(folder) / "evidence.enc.json"
            public.write_bytes(public_bytes)
            stdout = StringIO()
            call_command(
                "export_wcu_syllabus_lineage_diagnostic",
                actor=self.actor.username,
                public_key=str(public),
                output=str(output),
                stdout=stdout,
            )
            self.assertRegex(stdout.getvalue(), r"^encrypted_sha256=[a-f0-9]{64} roots=1 cycles=2\n$")
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with (
                patch.object(decoder, "KEY_FINGERPRINT", fingerprint),
                patch.object(decoder, "validator", return_value=self.scope()),
            ):
                value = decoder.decrypt_snapshot(output.read_bytes(), private_bytes)
                self.assertEqual(value["counts"]["cycles"], 2)
                changed = json.loads(output.read_bytes())
                cipher = bytearray(base64.b64decode(changed["ciphertext"]))
                cipher[0] ^= 1
                changed["ciphertext"] = base64.b64encode(cipher).decode()
                with self.assertRaises(InvalidTag):
                    decoder.decrypt_snapshot(json.dumps(changed).encode(), private_bytes)
                tampered = json.loads(output.read_bytes())
                tampered["format"] = "untrusted"
                with self.assertRaises(ValueError):
                    decoder.decrypt_snapshot(json.dumps(tampered).encode(), private_bytes)
            with patch.object(normal, "KEY_FINGERPRINT", fingerprint), self.assertRaises(ValueError):
                normal.decrypt_snapshot(output.read_bytes(), private_bytes)
            before = output.read_bytes()
            self.assertNotIn(b"PRIVATE_CONTACT", before)
            with self.assertRaises(FileExistsError):
                save_encrypted(self.capture(), public, output)
