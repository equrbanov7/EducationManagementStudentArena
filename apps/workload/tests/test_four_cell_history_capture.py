"""Migrated PG command/auth/crypto and independent fixed-four readonly capture."""

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
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.test import TransactionTestCase, override_settings

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.audit.models import AuditLog
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.workload.services import four_cell_history_capture as export
from apps.workload.services import scoped_snapshot
from apps.workload.services.scoped_snapshot import four_cell_history as probe
from apps.workload.services.syllabus_content_export import limits
from apps.workload.tests.factories import activate_member, make_structure
from apps.workload.tests.test_chair_cells_export import ChairCellsExportTests as Fixture

ROOT = Path(__file__).resolve().parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class FourCellCaptureTests(TransactionTestCase):
    setUp_base = Fixture.setUp
    new_offering = Fixture.new_offering

    def setUp(self):
        self.setUp_base()
        self.targets = {}
        for index, oid in enumerate(sorted({c["offering_id"] for c in probe.CASES.values()})):
            stack = make_structure(self.org, code="FOUR" + str(index))
            self.targets[oid] = CourseOffering.objects.create(
                id=oid,
                organization=self.org,
                subject=stack["subject"],
                group=stack["group"],
                period=self.stack["period"],
                lesson_hours=30,
            )
        for point, c in probe.CASES.items():
            user = get_user_model().objects.create_user(id=c["student_id"], username="PRIVATE_STUDENT_" + str(point))
            activate_member(self.org, user, "four_reader_student", permissions=["course.view"])
            user.profile.organization = self.org
            user.profile.save(update_fields=["organization"])
            Enrollment.objects.create(
                id=c["enrollment_id"], organization=self.org, student=user, offering=self.targets[c["offering_id"]]
            )
            Lesson.objects.get_or_create(
                id=c["lesson_id"],
                defaults={
                    "organization": self.org,
                    "offering": self.targets[c["offering_id"]],
                    "date": c["date"],
                    "start_time": c["start_time"],
                    "kind": c["kind"],
                    "hours": 2,
                },
            )
        c = probe.CASES[5458056]
        self.audit = AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="update",
            resource_type="registrar.grade.full-edit",
            resource_id=c["offering_id"],
            changes=[{"enrollment_id": c["enrollment_id"], "lesson_id": c["lesson_id"], "old": "q/b", "new": "—"}],
            old_values={"PASSWORD": "PRIVATE_CONTACT"},
            reason="PRIVATE_REASON",
        )

    def encoded(self, value):
        return json.loads(json.dumps(value, cls=DjangoJSONEncoder))

    def fingerprint(self):
        return self.encoded(
            {
                "marks": list(LessonMark.objects.values()),
                "enrollments": list(Enrollment.objects.values()),
                "audit": list(AuditLog.objects.values()),
            }
        )

    def test_full_readonly_capture_both_rls_and_strict_standalone_decoder_scope(self):
        validator = load("four_scope", ROOT / "scripts/ops/four_cell_history_scope.py")
        before = self.fingerprint()
        for mode in [False, True]:
            with self.subTest(mode=mode), override_settings(RLS_TRANSACTION_SCOPED=mode):
                value = self.encoded(export.capture(self.actor.username))
                validator.validate(value)
                self.assertEqual(value["counts"]["four_cell_history_current"], 8)
                self.assertEqual(value["source_spec_sha256"], validator.SPEC_SHA)
                self.assertFalse(value["eligible_for_apply"])
                self.assertNotIn("PRIVATE", json.dumps(value))
        self.assertEqual(before, self.fingerprint())

    def test_foreign_inactive_non_superuser_actor_and_nested_transactions_refused(self):
        User = get_user_model()
        foreign = User.objects.create_superuser("FOREIGN_SECRET", password="AUTH_SECRET")
        foreign.profile.organization = None
        foreign.profile.save(update_fields=["organization"])
        inactive = User.objects.create_superuser("INACTIVE_SECRET", password="AUTH_SECRET", is_active=False)
        for user in [foreign, inactive, self.student]:
            with self.assertRaisesRegex(ValueError, "active_fixed_tenant_superuser_required"):
                export.capture(user.username)
        with transaction.atomic():
            with self.assertRaisesRegex(ValueError, "fresh_postgresql_transaction_required"):
                export.capture(self.actor.username)

    def test_actual_command_has_only_fixed_read_inputs_and_safe_failure(self):
        output = StringIO()
        with patch(
            "apps.workload.management.commands.export_wcu_four_cell_history.capture",
            side_effect=RuntimeError("PASSWORD_PRIVATE_CONTACT"),
        ):
            with self.assertRaises(CommandError) as caught:
                call_command("export_wcu_four_cell_history", actor="x", public_key="x", output="x", stdout=output)
        self.assertEqual(str(caught.exception), "four_cell_history_export_refused")
        self.assertEqual(output.getvalue(), "")
        from apps.workload.management.commands.export_wcu_four_cell_history import Command

        options = {a.dest for a in Command().create_parser("manage.py", "export_wcu_four_cell_history")._actions}
        self.assertFalse({"apply", "undo", "student", "lesson", "offering", "source", "case"} & options)

    def test_query_time_and_output_caps_no_writes(self):
        before = self.fingerprint()
        for key, value in [("MAX_QUERIES", 0), ("MAX_SECONDS", 0)]:
            with patch.object(limits, key, value):
                with self.assertRaises(ValueError):
                    export.capture(self.actor.username)
        with patch.object(export, "MAX_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "output_budget"):
                export.capture(self.actor.username)
        self.assertEqual(before, self.fingerprint())

    def test_authenticated_crypto_new_file_only_and_schema_tamper_rejected(self):
        value = export.capture(self.actor.username)
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        public = key.public_key()
        der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        private = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        decoder = load("four_decoder", ROOT / "scripts/ops/decrypt_four_cell_history.py")
        fingerprint = hashlib.sha256(der).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            pub = folder / "public.pem"
            pub.write_bytes(
                public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            )
            cipher = folder / "snapshot.enc.json"
            with (
                patch.object(scoped_snapshot, "KEY_FINGERPRINT", fingerprint),
                patch.object(decoder, "KEY_FINGERPRINT", fingerprint),
            ):
                sha = export.save_encrypted(value, pub, cipher)
                self.assertEqual(sha, hashlib.sha256(cipher.read_bytes()).hexdigest())
                decoded = decoder.decrypt_snapshot(cipher.read_bytes(), private)
                self.assertEqual(decoded, self.encoded(value))
                out = decoder.write_new_snapshot(decoded, folder)
                self.assertEqual(out.stat().st_mode & 0o777, 0o600)
                self.assertEqual(cipher.stat().st_mode & 0o777, 0o600)
                with self.assertRaises(FileExistsError):
                    export.save_encrypted(value, pub, cipher)
                bad = copy.deepcopy(value)
                bad["data"]["four_cell_history_scope"][0]["note"] = "PRIVATE_CONTACT"
                badfile = folder / "bad.enc.json"
                export.save_encrypted(bad, pub, badfile)
                with self.assertRaises(ValueError):
                    decoder.decrypt_snapshot(badfile.read_bytes(), private)
                corrupted = json.loads(cipher.read_bytes())
                corrupted["ciphertext"] = corrupted["ciphertext"][:-4] + "AAAA"
                with self.assertRaises(InvalidTag):
                    decoder.decrypt_snapshot(json.dumps(corrupted).encode(), private)


del Fixture
