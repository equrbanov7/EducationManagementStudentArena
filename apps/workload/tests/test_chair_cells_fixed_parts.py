"""Real PostgreSQL: fixed10-root parts retain old25 TOTAL history limit and privacy."""

import base64
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
from django.db import connection, transaction
from django.test import TransactionTestCase, override_settings

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.workload.services import chair_cells_fixed_parts as parts
from apps.workload.services import scoped_snapshot as crypto
from apps.workload.services.chair_cells_export import capture as old_capture
from apps.workload.services.chair_cells_export.collect import SCHEMAS
from apps.workload.services.chair_cells_export.spec import batch_spec
from apps.workload.services.scoped_snapshot import SnapshotError
from apps.workload.tests import test_chair_cells_export as old_fixture
from apps.workload.tests.factories import make_org, make_structure

ROOT = Path(__file__).resolve().parents[3]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


class FixedJournalPartsTests(TransactionTestCase):
    new_offering = old_fixture.ChairCellsExportTests.new_offering

    def setUp(self):
        old_fixture.ChairCellsExportTests.setUp(self)
        self.roots, self.current = [], []
        for index in range(20):
            if index == 0:
                offering, enrollment = self.offering, self.enrollment
            else:
                offering = self.extra_course(f"root-{index}")
                enrollment = Enrollment.objects.create(organization=self.org, offering=offering, student=self.student)
            previous = self.extra_course(f"history-{index}", is_active=False)
            old = Enrollment.objects.create(
                organization=self.org,
                offering=previous,
                student=self.student,
                status="dropped",
                superseded_by=enrollment,
            )
            lesson = Lesson.objects.create(
                organization=self.org, offering=previous, date="2026-09-21", kind="seminar", created_by=self.actor
            )
            LessonMark.objects.create(organization=self.org, enrollment=old, lesson=lesson, status="absent")
            self.roots.append({"id": str(offering.pk), "chair_id": None, "classification": "unassigned"})
            self.current.append(enrollment)
        self.spec["offerings"] = self.roots
        self.parent_pin = patch.object(parts, "parent_spec", return_value=self.spec)
        self.parent_pin.start()
        self.addCleanup(self.parent_pin.stop)
        self.scope = module("new_part_scope", ROOT / "scripts/ops/journal_cells_part_scope.py")
        self.decoder = module("new_part_decoder", ROOT / "scripts/ops/decrypt_journal_cells_part.py")
        self.scope_pin = patch.object(self.scope, "parent_spec", return_value=self.spec)
        self.scope_pin.start()
        self.addCleanup(self.scope_pin.stop)
        self.validator_pin = patch.object(self.decoder, "validator", return_value=self.scope)
        self.validator_pin.start()
        self.addCleanup(self.validator_pin.stop)

    def extra_course(self, suffix, **kwargs):
        group = OrgUnit.objects.create(
            organization=self.org, name=suffix, slug=suffix, unit_type="group", parent=self.stack["specialty"]
        )
        return CourseOffering.objects.create(
            organization=self.org, subject=self.stack["subject"], period=self.stack["period"], group=group, **kwargs
        )

    def capture(self, name="chair-cells-043-part-001"):
        result = parts.capture(self.actor.username, name)
        return json.loads(json.dumps(result, cls=DjangoJSONEncoder))

    def test_parent40_fails_but_independent_halves20_each_preserve_every_cell(self):
        original = list(LessonMark.objects.order_by("pk").values())
        with self.assertRaisesRegex(SnapshotError, "history_course_budget"):
            old_capture(self.actor.username, "chair-cells-043")
        snapshots = [self.capture(name) for name in ("chair-cells-043-part-001", "chair-cells-043-part-002")]
        for payload in snapshots:
            self.assertEqual(payload["counts"]["offerings"], 20)
            self.assertEqual(len(payload["selection"]["offerings"]), 10)
            self.scope.validate(payload)
        self.assertEqual(
            {r["id"] for p in snapshots for r in p["selection"]["offerings"]}, {r["id"] for r in self.roots}
        )
        self.assertEqual({r["id"] for p in snapshots for r in p["data"]["marks"]}, {str(r["id"]) for r in original})
        logical = self.scope.validate_pair(*snapshots)
        self.assertTrue(logical["complete"])
        self.assertNotIn("path", logical)
        self.assertNotIn("format", logical)
        self.assertEqual(original, list(LessonMark.objects.order_by("pk").values()))

    def test_exact_pinned_selectors_ordered_parent_roots_no_arbitrary_ids(self):
        self.parent_pin.stop()
        self.scope_pin.stop()
        try:
            self.assertEqual((len(parts.PARENTS), len(parts.PARTS)), (9, 18))
            self.assertEqual(parts.PARENTS, self.scope.PARENTS)
            self.assertEqual(parts.PARTS, self.scope.PARTS)
            self.assertEqual(len(batch_spec("chair-cells-070")["offerings"]), 2)
            self.assertEqual(len(batch_spec("chair-cells-091")["offerings"]), 18)
            for parent in parts.PARENTS:
                first, sha1, name1 = parts.selection(parent + "-part-001")
                second, sha2, name2 = parts.selection(parent + "-part-002")
                self.assertEqual(first["offerings"] + second["offerings"], batch_spec(parent)["offerings"])
                self.assertEqual((name1, name2, sha1), (parent, parent, sha2))
                self.assertEqual(self.scope.selection(parent + "-part-001"), (first, sha1))
                self.assertEqual(self.scope.selection(parent + "-part-002"), (second, sha2))
            for name in (
                "chair-cells-042-part-001",
                "chair-cells-043",
                "chair-cells-043-part-003",
                "$(id)",
                "chair-cells-070-part-001",
                "chair-cells-070-part-002",
                "chair-cells-091-part-001",
            ):
                with self.assertRaisesRegex(SnapshotError, "fixed_journal_part"):
                    parts.selection(name)
                with self.assertRaisesRegex(ValueError, "fixed_part"):
                    self.scope.selection(name)
        finally:
            self.parent_pin.start()
            self.scope_pin.start()

    def test_single26_course_component_still_fails_no_truncation_or_limit_raise(self):
        # One active root with25 direct dropped predecessors is a26-course component.
        # One predecessor already exists; create24 more.
        for index in range(24):
            previous = self.extra_course(f"wide-history-{index}")
            Enrollment.objects.create(
                organization=self.org,
                offering=previous,
                student=self.student,
                status="dropped",
                superseded_by=self.current[0],
            )
        with self.assertRaisesRegex(SnapshotError, "history_course_budget"):
            self.capture()
        self.assertEqual(CourseOffering.objects.count(), 64)
        self.assertEqual(len(self.spec["offerings"]), 20)

    def test_fresh_real_readonly_both_rls_modes_with_foreign_tenant_invisible(self):
        foreign = make_org("part-foreign")
        foreign_offering = self.new_offering(make_structure(foreign, code="PARTFOREIGN"))
        original = parts._capture

        def inspect(username, selection, batch):
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_read_only")
                self.assertEqual(cursor.fetchone()[0], "on")
                cursor.execute("SET LOCAL ROLE rls_app_role")
                cursor.execute("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname=current_user")
                self.assertEqual(cursor.fetchone(), (False, False))
            payload = original(username, selection, batch)
            self.assertFalse(CourseOffering.objects.filter(pk=foreign_offering.pk).exists())
            return payload

        for mode in (False, True):
            with (
                self.subTest(mode=mode),
                override_settings(RLS_TRANSACTION_SCOPED=mode),
                patch.object(parts, "_capture", side_effect=inspect),
            ):
                self.assertEqual(self.capture()["counts"]["offerings"], 20)
        with transaction.atomic(), self.assertRaisesRegex(SnapshotError, "fresh_postgresql"):
            self.capture()

    def test_readonly_rejects_writes_and_query_budget_is_existing_guard(self):
        def write(username, selection, batch):
            LessonMark.objects.filter(pk=self.mark.pk).update(score=1)

        with patch.object(parts, "_capture", side_effect=write):
            with self.assertRaises(Exception) as failure:
                self.capture()
        self.assertIn("read-only", str(failure.exception))
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.score, 7)
        original = parts._capture

        def over_budget(*args):
            for _ in range(110):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            return original(*args)

        with patch.object(parts, "_capture", side_effect=over_budget):
            with self.assertRaisesRegex(SnapshotError, "query_or_time_budget"):
                self.capture()

    def test_actor_and_cross_tenant_root_rejected(self):
        outsider = get_user_model().objects.create_superuser("part_outside_operator")
        with self.assertRaisesRegex(SnapshotError, "fixed_tenant_superuser"):
            parts.capture(outsider.username, parts.PARTS[0])
        self.spec["offerings"][0]["id"] = "00000000-0000-0000-0000-000000000001"
        with self.assertRaisesRegex(SnapshotError, "scope_changed"):
            self.capture()

    def test_strict_scope_refuses_header_privacy_ref_scope_order_and_false_counts(self):
        payload = self.capture()
        self.scope.validate(payload)
        cases = []

        def add(change):
            value = copy.deepcopy(payload)
            change(value)
            cases.append(value)

        add(lambda p: p.update(parent_batch="chair-cells-042"))
        add(lambda p: p.update(part="chair-cells-043-part-002"))
        add(lambda p: p["selection"]["offerings"].reverse())
        add(lambda p: p.update(pin="PRIVATE_PIN_SENTINEL"))
        add(lambda p: p["data"]["marks"][0].update(note="PRIVATE_NOTE_SENTINEL"))
        add(lambda p: p["data"]["marks"][0].update(lesson_id="00000000-0000-0000-0000-000000000001"))
        add(lambda p: p["data"]["enrollments"][0].update(superseded_by_id="00000000-0000-0000-0000-000000000001"))
        add(lambda p: p["counts"].update(marks=True))
        add(lambda p: p["data"]["offerings"].append(copy.deepcopy(p["data"]["offerings"][0])))
        for value in cases:
            with self.subTest(case=cases.index(value)), self.assertRaises(ValueError):
                self.scope.validate(value)
        for table, schema in SCHEMAS.items():
            self.assertEqual(set(payload["schema_fields"][table]), set(schema))
        self.assertNotIn("SENTINEL", json.dumps(payload))

    def test_authenticated_roundtrip_separate_part_files_tamper_and_command_privacy(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        public = private.public_key()
        der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        fingerprint = hashlib.sha256(der).hexdigest()
        secret = private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(crypto, "KEY_FINGERPRINT", fingerprint),
            patch.object(self.decoder, "KEY_FINGERPRINT", fingerprint),
        ):
            folder = Path(directory)
            public_path = folder / "public.pem"
            public_path.write_bytes(
                public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            )
            for part in ("chair-cells-043-part-001", "chair-cells-043-part-002"):
                output = folder / (part + ".enc.json")
                stdout = StringIO()
                call_command(
                    "export_wcu_journal_cells_part",
                    actor=self.actor.username,
                    part=part,
                    public_key=str(public_path),
                    output=str(output),
                    stdout=stdout,
                )
                self.assertIn("roots=10 offerings=20", stdout.getvalue())
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
                payload = self.decoder.decrypt_snapshot(output.read_bytes(), secret)
                self.assertEqual(payload["part"], part)
                self.assertEqual(payload["counts"]["offerings"], 20)
                plain = self.decoder.write_new_snapshot(payload, folder)
                self.assertEqual(plain.stat().st_mode & 0o777, 0o600)
                envelope = json.loads(output.read_bytes())
                ciphertext = bytearray(base64.b64decode(envelope["ciphertext"]))
                ciphertext[-1] ^= 1
                envelope["ciphertext"] = base64.b64encode(ciphertext).decode()
                with self.assertRaises(InvalidTag):
                    self.decoder.decrypt_snapshot(json.dumps(envelope).encode(), secret)
            with self.assertRaisesRegex(CommandError, "fixed_journal_part"):
                call_command(
                    "export_wcu_journal_cells_part",
                    actor=self.actor.username,
                    part="PRIVATE_BAD_SELECTOR",
                    public_key=str(public_path),
                    output=str(folder / "invalid"),
                )
            with patch(
                "apps.workload.management.commands.export_wcu_journal_cells_part.capture",
                side_effect=RuntimeError("PRIVATE_SECRET_SENTINEL"),
            ):
                with self.assertRaisesMessage(CommandError, "journal_part_export_refused"):
                    call_command(
                        "export_wcu_journal_cells_part",
                        actor=self.actor.username,
                        part=parts.PARTS[0],
                        public_key=str(public_path),
                        output=str(folder / "invalid"),
                    )
