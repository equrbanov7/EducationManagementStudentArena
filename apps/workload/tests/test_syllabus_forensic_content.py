"""Twenty-root fingerprint capsules retain bad draft edges but never assert valid lineage."""

import copy
import hashlib
import json
import tempfile
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.core.management import call_command
from django.db import DatabaseError
from django.test import TransactionTestCase, override_settings

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.workload.services import syllabus_content_export as normal
from apps.workload.services import syllabus_forensic_capture as forensic
from apps.workload.services import syllabus_forensic_spec as contract
from apps.workload.services.scoped_snapshot import SnapshotError
from apps.workload.services.syllabus_content_export import spec
from apps.workload.tests import test_syllabus_content_export as fixture


class ForensicBodyTests(TransactionTestCase):
    new_offering = fixture.SyllabusContentExportTests.new_offering
    _setup_fixture = fixture.SyllabusContentExportTests._setup_fixture
    document = fixture.SyllabusContentExportTests.document

    def setUp(self):
        fixture.SyllabusContentExportTests.setUp(self)
        self.documents = [self.document_syllabus]
        courses = [self.offering]
        for index in range(19):
            group = apps.get_model("organizations.OrgUnit").objects.create(
                organization=self.org,
                parent=self.stack["specialty"],
                unit_type="group",
                name=f"Forensic{index}",
                slug=f"forensic-{index}",
            )
            offering = self.new_offering({**self.stack, "group": group}, instructor=self.actor)
            courses.append(offering)
            if index == 0:
                Syllabus.objects.filter(pk=self.base.pk).update(offering=offering, period=offering.period)
                self.documents.append(self.base)
            else:
                doc, _ = self.document(offering, offering.period)
                self.documents.append(doc)
        self.spec["offerings"] = [dict(id=str(o.pk), chair_id=None, classification="unassigned") for o in courses]
        SyllabusVersion.objects.filter(pk__in=[self.base_version.pk, self.approved.pk]).update(
            status="draft", approval_source="human", locked_at=None
        )
        Syllabus.objects.filter(pk__in=[self.base.pk, self.document_syllabus.pk]).update(approved_version=None)
        SyllabusVersion.objects.filter(pk=self.base_version.pk).update(source_version=self.approved)

    def capture(self, batch="chair-cells-027"):
        return forensic.capture(self.actor.username, batch)

    def snapshot(self):
        return (
            list(Syllabus.objects.order_by("pk").values()),
            list(SyllabusVersion.objects.order_by("pk").values()),
            list(SyllabusSection.objects.order_by("pk").values()),
            self.mark.__class__.objects.values().get(pk=self.mark.pk),
        )

    def test_all20_bodies_and_cycle_affected_roots_no_writes_or_raw_text(self):
        before = self.snapshot()
        result = self.capture()
        self.assertEqual(result["format"], contract.FORMAT)
        self.assertEqual(result["counts"]["roots"], 20)
        self.assertEqual(result["counts"]["sections"], 40)
        self.assertEqual(result["counts"]["topics"], 20)
        self.assertEqual(result["counts"]["lineage_cycles"], 1)
        self.assertEqual(result["coverage"]["cycle_affected_root_count"], 2)
        self.assertFalse(result["coverage"]["closure_complete"])
        self.assertFalse(result["coverage"]["lineage_integrity"])
        self.assertFalse(result["coverage"]["normal_content_export_usable"])
        self.assertTrue(result["coverage"]["lineage_visited_complete"])
        self.assertFalse(result["eligible_for_apply"])
        for text in ("PRIVATE_CONTACT", "MEANINGFUL_HISTORICAL_TEXT", "AUTHORED_TOPIC_SECRET", self.student.username):
            self.assertNotIn(text, json.dumps(result, default=str))
        self.assertEqual(self.snapshot(), before)
        with self.assertRaisesRegex(SnapshotError, "syllabus_lineage_cycle"):
            normal.capture(self.actor.username, "chair-cells-027")

    def test_only_compiled_two_batches_and_no_partial_cap_success(self):
        with self.assertRaisesRegex(SnapshotError, "root_scope"):
            self.capture("chair-cells-028")
        self.assertEqual(self.capture("chair-cells-029")["batch"], "chair-cells-029")
        with patch.object(spec, "MAX_SECTIONS", 39), self.assertRaises(SnapshotError):
            self.capture()
        with patch.object(spec, "MAX_SECTION_BYTES", 1), self.assertRaises(SnapshotError):
            self.capture()
        self.spec["offerings"].pop()
        with self.assertRaisesRegex(SnapshotError, "root_scope"):
            self.capture()

    def test_unknown_additional_cycle_is_listed_without_declaring_other_roots_affected(self):
        own = self.documents[2].current_version
        SyllabusVersion.objects.filter(pk=own.pk).update(source_version=own)
        result = self.capture()
        self.assertEqual(result["counts"]["lineage_cycles"], 2)
        self.assertEqual(result["coverage"]["cycle_affected_root_count"], 3)
        self.assertEqual(sum(not r["lineage_cycle_affected"] for r in result["data"]["held_roots"]), 17)

    def test_readonly_database_boundary_and_foreign_actor(self):
        def write(*args, **kwargs):
            Syllabus.objects.filter(pk=self.base.pk).update(is_active=False)

        with patch.object(normal, "collect", side_effect=write), self.assertRaises(DatabaseError):
            self.capture()
        self.base.refresh_from_db()
        self.assertTrue(self.base.is_active)
        outsider = apps.get_model("auth.User").objects.create_superuser("forensic-other")
        with self.assertRaisesRegex(SnapshotError, "superuser"):
            forensic.capture(outsider.username, "chair-cells-027")

    def test_actual_command_uses_distinct_format_and_safe_exception_output(self):
        from apps.workload.management.commands import export_wcu_syllabus_forensic as command

        output = StringIO()
        with patch.object(command, "save_encrypted", return_value="0" * 64) as save:
            call_command(
                "export_wcu_syllabus_forensic",
                actor=self.actor.username,
                batch="chair-cells-027",
                public_key="unused",
                output="unused",
                stdout=output,
            )
        self.assertEqual(save.call_args.args[0]["format"], contract.FORMAT)
        error = StringIO()
        with (
            patch.object(command, "capture", side_effect=ValueError("private_contact_sql")),
            self.assertRaises(Exception) as exc,
        ):
            call_command(
                "export_wcu_syllabus_forensic",
                actor=self.actor.username,
                batch="chair-cells-027",
                public_key="unused",
                output="unused",
                stderr=error,
            )
        self.assertNotIn("private_contact_sql", str(exc.exception) + error.getvalue())

    def test_authenticated_decoder_schema_and_cycle_flags_cannot_be_promoted(self):
        result = self.capture()
        decoder = fixture.load_script("decrypt_syllabus_forensic")
        validator = fixture.load_script("syllabus_content_scope")
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        public = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        private = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        fingerprint = hashlib.sha256(der).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            registry = root / "registry.json"
            registry.write_text(json.dumps({"batches": {batch: self.spec for batch in contract.BATCHES}}))
            sha = hashlib.sha256(registry.read_bytes()).hexdigest()
            result["registry_sha256"] = sha
            public_path = root / "public.pem"
            public_path.write_bytes(public)
            adapter = SimpleNamespace(
                MAX_BYTES=validator.MAX_BYTES, validate=lambda payload: validator._validate(payload, _forensic=True)
            )
            with (
                patch("apps.workload.services.scoped_snapshot.KEY_FINGERPRINT", fingerprint),
                patch.object(decoder, "KEY_FINGERPRINT", fingerprint),
                patch.object(decoder, "validator", return_value=adapter),
                patch.object(validator, "REGISTRY_PATH", registry),
                patch.object(validator, "REGISTRY_SHA", sha),
            ):
                cipher = root / "content.enc"
                normal.save_encrypted(result, public_path, cipher)
                payload = decoder.decrypt_snapshot(cipher.read_bytes(), private)
                output = decoder.write_new_snapshot(payload, root)
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
                with self.assertRaises(ValueError):
                    validator.validate(payload)
                promoted = copy.deepcopy(payload)
                promoted["format"] = spec.FORMAT
                for name in contract.SCHEMAS:
                    for section in ("data", "counts", "schema_fields"):
                        promoted[section].pop(name)
                for name in (
                    "lineage_visited_complete",
                    "lineage_integrity",
                    "normal_content_export_usable",
                    "cycle_affected_root_count",
                ):
                    promoted["coverage"].pop(name)
                promoted["coverage"]["closure_complete"] = True
                with self.assertRaises(ValueError):
                    validator.validate(promoted)
                for mutate in (
                    lambda p: p["coverage"].update(normal_content_export_usable=True),
                    lambda p: p["data"]["lineage_cycles"].clear(),
                    lambda p: p["data"]["sections"][0].update(raw_body="PRIVATE"),
                    lambda p: p["data"]["held_roots"][0].update(lineage_cycle_affected=1),
                ):
                    bad = copy.deepcopy(payload)
                    mutate(bad)
                    with self.assertRaises(ValueError):
                        adapter.validate(bad)
                envelope = json.loads(cipher.read_bytes())
                envelope["ciphertext"] = envelope["ciphertext"][:-4] + "AAAA"
                with self.assertRaises((InvalidTag, ValueError)):
                    decoder.decrypt_snapshot(json.dumps(envelope).encode(), private)


@override_settings(RLS_TRANSACTION_SCOPED=True)
class ForensicBodyTransactionScopedTests(ForensicBodyTests):
    pass
