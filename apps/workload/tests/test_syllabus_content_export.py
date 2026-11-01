"""Migrated PG: actual canonical closure, base/null history, crypto and no content/grade writes."""

import copy
import hashlib
import importlib.util
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusShare, SyllabusVersion
from apps.workload.services import syllabus_content_export as export
from apps.workload.services.scoped_snapshot import SnapshotError
from apps.workload.services.syllabus_content_export import limits, spec
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org
from apps.workload.tests.test_chair_cells_export import ChairCellsExportTests as Fixture

ROOT = Path(__file__).resolve().parents[3]


def load_script(name):
    target = ROOT / f"scripts/ops/{name}.py"
    description = importlib.util.spec_from_file_location(name, target)
    result = importlib.util.module_from_spec(description)
    description.loader.exec_module(result)
    return result


class SyllabusContentExportTests(TransactionTestCase):
    new_offering = Fixture.new_offering
    _setup_fixture = Fixture.setUp

    def setUp(self):
        self._setup_fixture()
        activate_member(self.org, self.actor, "syllabus_audit_teacher", permissions=TEACHER_PERMS)
        self.offering.instructor = self.actor
        self.offering.save(update_fields=["instructor"])
        self.select_pin = patch.object(spec, "batch_spec", return_value=self.spec)
        self.select_pin.start()
        self.addCleanup(self.select_pin.stop)
        self.base, self.base_version = self.document(None, None)
        self.document_syllabus, self.approved = self.document(self.offering, self.offering.period)
        self.approved.source_version = self.base_version
        self.approved.save(update_fields=["source_version"])

    def document(self, offering, period, *, organization=None, subject=None, author=None):
        org = organization or self.org
        syllabus = Syllabus.objects.create(
            organization=org,
            subject=subject or self.offering.subject,
            offering=offering,
            period=period,
            author=author or self.actor,
        )
        version = SyllabusVersion.objects.create(
            organization=org,
            syllabus=syllabus,
            status="approved",
            approval_source="migration",
            locked_at=timezone.now(),
            plan_hours={"lecture": 30, "seminar": 15},
            completion_percent=67,
        )
        Syllabus.objects.filter(pk=syllabus.pk).update(current_version=version, approved_version=version)
        SyllabusSection.objects.create(
            organization=org,
            version=version,
            section_id="info",
            data={"teacher": "PRIVATE_CONTACT", "welcome": "MEANINGFUL_HISTORICAL_TEXT"},
        )
        SyllabusSection.objects.create(
            organization=org,
            version=version,
            section_id="week",
            data={"rows": [{"topic": "AUTHORED_TOPIC_SECRET", "lecture": 2, "seminar": 0, "lab": 0, "outcome": "TN1"}]},
        )
        return Syllabus.objects.get(pk=syllabus.pk), version

    def capture(self):
        return export.capture(self.actor.username, "chair-cells-001")

    def test_current_approved_source_ancestry_and_null_base_body_are_complete_without_raw_text(self):
        draft = SyllabusVersion.objects.create(
            organization=self.org, syllabus=self.document_syllabus, major=2, plan_hours={"lecture": 30}
        )
        Syllabus.objects.filter(pk=self.document_syllabus.pk).update(current_version=draft, approved_version=None)
        self.mark.refresh_from_db()
        before = self.mark.__class__.objects.values().get(pk=self.mark.pk)
        result = self.capture()
        root = result["data"]["roots"][0]
        self.assertEqual(root["current_version_id"], draft.pk)
        self.assertEqual(root["effective_approved_version_id"], self.approved.pk)
        self.assertEqual(
            {v["id"] for v in result["data"]["versions"]}, {draft.pk, self.approved.pk, self.base_version.pk}
        )
        self.assertEqual(
            {s["id"] for s in result["data"]["syllabi"] if s["body_included"]},
            {self.document_syllabus.pk, self.base.pk},
        )
        self.assertEqual(before, self.mark.__class__.objects.values().get(pk=self.mark.pk))
        encoded = json.dumps(result, default=str)
        for text in (
            "PRIVATE_CONTACT",
            "MEANINGFUL_HISTORICAL_TEXT",
            "AUTHORED_TOPIC_SECRET",
            self.student.username,
            '"password"',
            '"decision_reason"',
            '"data": {"teacher"',
        ):
            self.assertNotIn(text, encoded)

    def test_unbound_all_author_candidates_include_inactive_and_other_period_without_absence_claim(self):
        other = get_user_model().objects.create_user("candidate_other")
        candidate = Syllabus.objects.create(
            organization=self.org, subject=self.offering.subject, author=other, is_active=False
        )
        result = self.capture()
        found = next(s for s in result["data"]["syllabi"] if s["id"] == candidate.pk)
        self.assertFalse(found["body_included"])
        self.assertFalse(found["is_active"])
        self.assertTrue(result["data"]["roots"][0]["base_candidates_complete"])
        self.assertFalse(result["coverage"]["absence_claim"])

    def test_shared_source_resolver_fetches_selected_source_body_outside_period_metadata(self):
        Syllabus.objects.filter(pk=self.document_syllabus.pk).delete()
        # An exact second physical group is needed for the separate source opening.
        from apps.organizations.models import OrgUnit

        group = OrgUnit.objects.create(
            organization=self.org, parent=self.stack["specialty"], unit_type="group", name="SECOND", slug="second-audit"
        )
        source = self.new_offering({**self.stack, "group": group}, instructor=self.actor)
        doc, version = self.document(source, source.period)
        SyllabusShare.objects.create(
            organization=self.org, offering=self.offering, syllabus=doc, source="legacy", created_by=self.actor
        )
        result = self.capture()
        self.assertEqual(result["data"]["roots"][0]["selected_syllabus_id"], doc.pk)
        self.assertIn(version.pk, {v["id"] for v in result["data"]["versions"]})
        self.assertTrue(result["data"]["shares"][0]["effective"])
        self.assertEqual(len(result["data"]["offerings"]), 2)
        with patch.object(spec, "MAX_COURSES", 1), self.assertRaisesRegex(SnapshotError, "row_budget"):
            self.capture()

    def test_both_rls_modes_use_readonly_actual_collector_and_never_select_auth_secrets(self):
        def inspect(execute, sql, params, many, context):
            if 'FROM "auth_user"' in sql:
                selected = sql.split(" FROM ", 1)[0]
                for field in ("password", "email", "first_name", "last_name", "username"):
                    self.assertNotIn('"' + field + '"', selected)
            return execute(sql, params, many, context)

        for mode in (False, True):
            with self.settings(RLS_TRANSACTION_SCOPED=mode), connection.execute_wrapper(inspect):
                result = self.capture()
                self.assertTrue(result["read_only"])
                self.assertEqual(result["organization_id"], spec.ORG)

    def test_write_on_read_fails_in_database_and_rolls_back_everything(self):
        before = Syllabus.objects.count()

        def write(_selection):
            Syllabus.objects.filter(pk=self.base.pk).update(is_active=False)

        with patch.object(export, "collect", side_effect=write):
            with self.assertRaises(Exception) as raised:
                self.capture()
        self.assertIn("read-only", str(raised.exception))
        self.base.refresh_from_db()
        self.assertTrue(self.base.is_active)
        self.assertEqual(Syllabus.objects.count(), before)

    def test_foreign_tenant_actor_and_foreign_selected_body_fail_closed(self):
        outsider = get_user_model().objects.create_superuser("outsider_syllabus_audit", password="PRIVATE")
        foreign_org = make_org("other-audit", owner=outsider)
        outsider.profile.organization = foreign_org
        outsider.profile.save(update_fields=["organization"])
        with self.assertRaisesRegex(SnapshotError, "fixed_tenant_superuser"):
            export.capture(outsider.username, "chair-cells-001")
        foreign = copy.copy(self.base)
        foreign.organization_id = foreign_org.pk
        with patch(
            "apps.workload.services.syllabus_content_export.collect.syllabus_for_offering", return_value=foreign
        ):
            with self.assertRaisesRegex(SnapshotError, "tenant_mismatch"):
                self.capture()
        with transaction.atomic(), self.assertRaisesRegex(SnapshotError, "fresh_postgresql"):
            self.capture()

    def test_limits_refuse_entire_batch_and_never_emit_truncated_output(self):
        for name, limit in (
            ("MAX_SECTIONS", 0),
            ("MAX_BODY_SYLLABI", 0),
            ("MAX_TOPICS", 0),
            ("MAX_ROWS", 0),
            ("MAX_OUTPUT_BYTES", 1),
            ("MAX_SECTION_BYTES", 1),
            ("MAX_VERSIONS", 0),
            ("MAX_COURSES", 0),
        ):
            with self.subTest(name=name), patch.object(spec, name, limit), self.assertRaises(ValueError):
                self.capture()
        with patch.object(limits, "MAX_QUERIES", 0), self.assertRaisesRegex(SnapshotError, "query_or_time"):
            self.capture()
        with patch.object(limits, "MAX_SECONDS", -1), self.assertRaisesRegex(SnapshotError, "query_or_time"):
            self.capture()

    def test_legacy_binding_ids_and_unknown_opaque_source_are_hash_only(self):
        from django.apps import apps

        run_model = apps.get_model("legacy_import.LegacyMigrationRun")
        mapping_model = apps.get_model("legacy_import.LegacyEntityMap")
        run = run_model.objects.create(
            organization=self.org,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            schema_version="v1",
            transform_version="v1",
            mode="profile",
        )
        run_model.objects.filter(pk=run.pk).update(status="running", started_at=timezone.now())
        record = mapping_model.objects.create(
            organization=self.org,
            source_system="myedu_mariadb",
            entity_type="syllabus",
            legacy_pk="PRIVATE_OPAQUE_SOURCE",
            source_row_hash="b" * 64,
            transform_version="v1",
            target_model_label="syllabus.syllabus",
            target_pk=str(self.base.pk),
            created_run=run,
            state="migrated",
        )
        section = SyllabusSection.objects.get(version=self.base_version, section_id="info")
        section_binding = mapping_model.objects.create(
            organization=self.org,
            source_system="myedu_mariadb",
            entity_type="syllabus_section",
            legacy_pk="4321",
            source_row_hash="c" * 64,
            transform_version="v1",
            target_model_label="syllabus.syllabussection",
            target_pk=str(section.pk),
            created_run=run,
            state="migrated",
        )
        result = self.capture()
        rows = result["data"]["ledger"]
        self.assertEqual({r["id"] for r in rows}, {record.pk, section_binding.pk})
        self.assertIsNone(next(r for r in rows if r["id"] == record.pk)["legacy_numeric_id"])
        self.assertEqual(next(r for r in rows if r["id"] == section_binding.pk)["legacy_numeric_id"], 4321)
        self.assertNotIn("PRIVATE_OPAQUE_SOURCE", json.dumps(result, default=str))

    def test_current_owner_reuses_existing_own_syllabus_without_rewriting_old_author(self):
        new_owner = get_user_model().objects.create_user("canonical_new_owner")
        activate_member(self.org, new_owner, "canonical_audit_teacher", permissions=TEACHER_PERMS)
        self.offering.instructor = new_owner
        self.offering.save(update_fields=["instructor"])
        result = self.capture()
        root = result["data"]["roots"][0]
        self.assertEqual(root["selected_syllabus_id"], self.document_syllabus.pk)
        self.assertEqual(root["relation"], "own")
        document = next(s for s in result["data"]["syllabi"] if s["id"] == self.document_syllabus.pk)
        self.assertEqual(document["author_id"], self.actor.pk)
        self.document_syllabus.refresh_from_db()
        self.assertEqual(self.document_syllabus.author_id, self.actor.pk)

    def test_compressed_large_json_is_bounded_by_logical_bytes_before_fetch(self):
        SyllabusSection.objects.filter(version=self.approved, section_id="info").update(data={"welcome": "x" * 10000})
        with (
            patch.object(spec, "MAX_SECTION_BYTES", 1000),
            self.assertRaisesRegex(SnapshotError, "source_body_byte_budget"),
        ):
            self.capture()

    def test_effective_null_period_base_is_resolved_and_inactive_owned_history_is_retained(self):
        Syllabus.objects.filter(pk=self.document_syllabus.pk).update(is_active=False)
        result = self.capture()
        self.assertEqual(result["data"]["roots"][0]["selected_syllabus_id"], self.base.pk)
        self.assertEqual(result["data"]["roots"][0]["relation"], "base")
        historical = next(r for r in result["data"]["syllabi"] if r["id"] == self.document_syllabus.pk)
        self.assertTrue(historical["body_included"])
        self.assertFalse(historical["is_active"])
        self.assertIn(self.base_version.pk, {v["id"] for v in result["data"]["versions"]})
        self.assertFalse(result["coverage"]["absence_claim"])

    def test_lineage_cycles_are_rejected_without_silently_marking_closure_complete(self):
        SyllabusVersion.objects.filter(pk=self.base_version.pk).update(source_version=self.approved)
        with self.assertRaisesRegex(SnapshotError, "lineage_cycle"):
            self.capture()

    def test_new_command_scrubs_unknown_exceptions_and_accepts_no_arbitrary_ids(self):
        with patch(
            "apps.workload.management.commands.export_wcu_syllabus_content.capture",
            side_effect=RuntimeError("PRIVATE_SOURCE_JSON_AND_CONTACT"),
        ):
            with self.assertRaisesMessage(CommandError, "syllabus_content_export_refused"):
                call_command(
                    "export_wcu_syllabus_content",
                    actor=self.actor.username,
                    batch="chair-cells-001",
                    public_key="unused",
                    output="unused",
                    stdout=StringIO(),
                )

    def test_authenticated_roundtrip_new_decoder_strict_schema_and_private_file(self):
        snapshot = self.capture()
        decoder, validator = load_script("decrypt_syllabus_content"), load_script("syllabus_content_scope")
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        public = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        fingerprint = hashlib.sha256(der).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            registry = path / "registry.json"
            registry.write_text(json.dumps({"batches": {"chair-cells-001": self.spec}}))
            registry_sha = hashlib.sha256(registry.read_bytes()).hexdigest()
            snapshot["registry_sha256"] = registry_sha
            (path / "public.pem").write_bytes(public)
            with (
                patch("apps.workload.services.scoped_snapshot.KEY_FINGERPRINT", fingerprint),
                patch.object(decoder, "KEY_FINGERPRINT", fingerprint),
                patch.object(decoder, "validator", return_value=validator),
                patch.object(validator, "REGISTRY_PATH", registry),
                patch.object(validator, "REGISTRY_SHA", registry_sha),
            ):
                encrypted = path / "snapshot.enc"
                export.save_encrypted(snapshot, path / "public.pem", encrypted)
                decoded = decoder.decrypt_snapshot(encrypted.read_bytes(), private)
                self.assertEqual(decoded["format"], spec.FORMAT)
                output = decoder.write_new_snapshot(decoded, path)
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
                self.assertEqual(encrypted.stat().st_mode & 0o777, 0o600)
                bad = copy.deepcopy(decoded)
                bad["data"]["sections"][0]["raw_text"] = "PRIVATE"
                with self.assertRaises(ValueError):
                    validator.validate(bad)
                envelope = json.loads(encrypted.read_bytes())
                envelope["ciphertext"] = envelope["ciphertext"][:-4] + "AAAA"
                with self.assertRaises((InvalidTag, ValueError)):
                    decoder.decrypt_snapshot(json.dumps(envelope).encode(), private)
                with self.assertRaises(FileExistsError):
                    export.save_encrypted(snapshot, path / "public.pem", encrypted)


# Reuse setup support, never recollect the existing journal exporter tests.
del Fixture
