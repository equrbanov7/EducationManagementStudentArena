"""Migrated PostgreSQL metadata export contracts; synthetic source identities only."""

import hashlib
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.accounts.models import UserProfile
from apps.organizations.models import OrgUnit
from apps.registrar.models import (
    Curriculum,
    Enrollment,
    JournalShare,
    LanguageLevelCohort,
    LanguageLevelPlacement,
    LessonMark,
    StudentAcademicRecord,
)
from apps.workload.management.commands.export_wcu_english_level_evidence import Command
from apps.workload.models import TeacherAssignment, TeachingTaskRow
from apps.workload.services import english_level_evidence as export
from apps.workload.services import scoped_snapshot
from apps.workload.services.scoped_snapshot import SnapshotError
from apps.workload.tests import test_chair_cells_export as fixture
from apps.workload.tests.factories import activate_member, make_org, make_task

spec = export.spec


class EnglishEvidenceBase(TransactionTestCase):
    new_offering = fixture.ChairCellsExportTests.new_offering

    def setUp(self):
        fixture.ChairCellsExportTests.setUp(self)
        UserProfile.objects.filter(user=self.actor).update(organization=self.org)
        UserProfile.objects.filter(user=self.student).update(
            organization=self.org,
            institutional_identifier="1",
            fin="AB12345",
            access_state="active",
        )
        activate_member(
            self.org,
            self.actor,
            "level-evidence-teacher",
            permissions=["grade.input", "course.view"],
        )
        self.offering.instructor = self.actor
        self.offering.save(update_fields=["instructor"])
        self.offering.subject.name = "Xarici dil-1(elementary)"
        self.offering.subject.save(update_fields=["name"])
        self.home = OrgUnit.objects.create(
            organization=self.org,
            unit_type="group",
            name="Home group",
            slug="level-evidence-home",
            parent=self.stack["specialty"],
        )
        curriculum = Curriculum.objects.create(
            organization=self.org, program=self.stack["program"], admission_year=2024
        )
        self.record = StudentAcademicRecord.objects.create(
            organization=self.org,
            student=self.student,
            program=self.stack["program"],
            curriculum=curriculum,
            group=self.home,
            admission_year=2024,
            status="enrolled",
            is_active=True,
        )
        self.enrollment.status = "dropped"
        self.enrollment.save(update_fields=["status"])
        group = self.offering.group
        group.settings = {"language_level_cohort": True, "sector": "az"}
        group.parent = self.stack["chair"]
        group.save(update_fields=["settings", "parent"])
        self.offering.lesson_hours = 30
        self.offering.save(update_fields=["lesson_hours"])
        self.cohort = LanguageLevelCohort.objects.create(
            organization=self.org,
            department=self.stack["chair"],
            group=group,
            offering=self.offering,
            period=self.offering.period,
            name="PRIVATE_COHORT_NAME",
            family="xarici dil-1",
            level="elementary",
            created_by=self.actor,
            seminar_hours=30,
        )
        self.placement = LanguageLevelPlacement.objects.create(
            organization=self.org,
            cohort=self.cohort,
            student=self.student,
            home_group=self.home,
            action="remove",
            source_enrollment=self.enrollment,
            actor=self.actor,
            reason="PRIVATE_RAW_REASON_URL_https://private.invalid/",
        )
        StudentAcademicRecord.objects.filter(pk=self.record.pk).update(status="graduated", is_active=False)
        UserProfile.objects.filter(user=self.student).update(access_state="archived")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "source.json"
        import hashlib

        rows = [
            {
                "id": i,
                "institutional_identifier": str(i),
                "normalized_fin": "AB12345" if i == 1 else "",
                "fin_sha256": (hashlib.sha256(b"AB12345").hexdigest() if i == 1 else None),
                "fin_valid": i == 1,
                "fin_present": i == 1,
                "source_row_sha256": "a" * 64,
            }
            for i in range(1, 1236)
        ]
        packet = {
            "format": spec.SOURCE_FORMAT,
            "organization_id": spec.ORG,
            "academic_year": spec.YEAR,
            "period_id": spec.PERIOD,
            "namespace": "myedu_new.students.id",
            "institutional_identifier_rule": "Canonical exact ID",
            "source_container": "ems-legacy-delta-src",
            "captured_at": "2026-10-01T00:00:00+00:00",
            "source_query_sha256": "a" * 64,
            "source_rows_sha256": "a" * 64,
            "roster_proof_sha256": "a" * 64,
            "source_ids_sha256": hashlib.sha256(
                json.dumps(list(range(1, 1236)), separators=(",", ":")).encode()
            ).hexdigest(),
            "records": rows,
        }
        self.file.write_text(json.dumps(packet))
        self.file.chmod(0o600)
        self.sha = hashlib.sha256(self.file.read_bytes()).hexdigest()
        for key, value in [
            ("SOURCE_SHA", self.sha),
            ("SOURCE_IDS_SHA", packet["source_ids_sha256"]),
            ("SUBJECTS", (str(self.offering.subject_id),)),
        ]:
            pin = patch.object(spec, key, value)
            pin.start()
            self.addCleanup(pin.stop)

    def capture(self):
        return export.capture(self.actor.username, self.file, self.sha)

    def test_actual_rr_scope_and_no_mutation_archive_dropped_human_preservation(self):
        before = (
            list(Enrollment.objects.values()),
            list(LessonMark.objects.values()),
            list(StudentAcademicRecord.objects.values()),
            list(LanguageLevelPlacement.objects.values()),
        )
        original = export.collect
        observed = []

        def watch(source):
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_setting('transaction_read_only'),current_setting('transaction_isolation'),current_setting('app.current_org_id'),current_setting('app.bypass_rls'),current_setting('app.current_user_id')"
                )
                observed.append(cursor.fetchone())
            return original(source)

        with patch.object(export, "collect", side_effect=watch):
            p = self.capture()
        self.assertEqual(observed, [("on", "repeatable read", spec.ORG, "off", str(self.actor.pk))])
        self.assertEqual(p["data"]["identity"][0]["target_user_id"], self.student.pk)
        self.assertFalse(p["data"]["identity"][0]["immutable_mapping"])
        self.assertEqual(p["data"]["profiles"][0]["access_state"], "archived")
        self.assertEqual(p["data"]["enrollments"][0]["status"], "dropped")
        self.assertEqual(p["data"]["academic_records"][0]["group_id"], str(self.home.pk))
        self.assertEqual(p["data"]["mark_activity"][0]["numeric_count"], 1)
        self.assertEqual(p["data"]["mark_activity"][0]["human_actor_count"], 1)
        self.assertEqual(
            before,
            (
                list(Enrollment.objects.values()),
                list(LessonMark.objects.values()),
                list(StudentAcademicRecord.objects.values()),
                list(LanguageLevelPlacement.objects.values()),
            ),
        )
        encoded = json.dumps(p)
        for sentinel in [
            "AB12345",
            self.student.username,
            "PRIVATE_COHORT_NAME",
            "PRIVATE_RAW_REASON_URL",
            "https://private.invalid/",
            '"score"',
            '"fin":',
            '"password"',
            '"email"',
        ]:
            self.assertNotIn(sentinel, encoded)

    def test_actual_command_owns_readonly_rls_transaction_and_cipher_only_output(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        public = key.public_key()
        pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        der = public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        public_path = Path(self.tmp.name) / "public.pem"
        public_path.write_bytes(pem)
        output = Path(self.tmp.name) / "evidence.enc.json"
        stdout = StringIO()
        with patch.object(scoped_snapshot, "KEY_FINGERPRINT", hashlib.sha256(der).hexdigest()):
            Command(stdout=stdout).handle(
                actor=self.actor.username,
                file=str(self.file),
                sha256=self.sha,
                public_key=str(public_path),
                output=str(output),
            )
        self.assertRegex(
            stdout.getvalue(), r"^encrypted_sha256=[a-f0-9]{64} identities=1235 offerings=1 placements=1\n$"
        )
        self.assertNotIn(self.actor.username, stdout.getvalue())
        self.assertNotIn("AB12345", output.read_text())
        self.assertEqual(json.loads(output.read_text())["format"], "wcu-workload-envelope/1")
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertFalse(connection.in_atomic_block)

    def test_database_rejects_any_accidental_write(self):
        with patch.object(
            export,
            "collect",
            side_effect=lambda source: get_user_model().objects.filter(pk=self.student.pk).update(is_active=False),
        ):
            with self.assertRaises(DatabaseError):
                self.capture()
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_foreign_actor_and_inactive_actor_fail_closed(self):
        foreign = get_user_model().objects.create_superuser("foreign-english-auditor", password="PRIVATE_SECRET")
        make_org("foreign-english", owner=foreign)
        with self.assertRaisesRegex(SnapshotError, "active_fixed_tenant_superuser_required"):
            export.capture(foreign.username, self.file, self.sha)
        get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
        with self.assertRaisesRegex(SnapshotError, "active_fixed_tenant_superuser_required"):
            self.capture()

    def test_caps_and_changed_source_fail_without_truncation(self):
        for field in ["MAX_COURSES", "MAX_ENROLLMENTS", "MAX_PLACEMENTS"]:
            with patch.object(spec, field, 0):
                with self.assertRaisesRegex(SnapshotError, "row_budget_exceeded"):
                    self.capture()
        with self.file.open("a") as stream:
            stream.write(" ")
        with self.assertRaisesRegex(SnapshotError, "source_digest_required"):
            self.capture()

    def test_owner_assignment_share_flags_exact_roster_and_no_write_authority(self):
        task = make_task(self.org, self.stack["chair"], status="approved")
        row = TeachingTaskRow.objects.create(
            organization=self.org,
            task=task,
            subject=self.offering.subject,
            period=self.offering.period,
            season="fall",
            lecture_plan=0,
            lecture_total=0,
            seminar_plan=30,
            seminar_total=30,
            total_hours=30,
        )
        row.groups.add(self.offering.group)
        assignment = TeacherAssignment.objects.create(
            organization=self.org,
            row=row,
            teacher=self.actor,
            activity="seminar",
            hours=30,
            groups_note="PRIVATE_GROUP_NOTE",
            note="PRIVATE_FREE_NOTE",
        )
        share = JournalShare.objects.create(
            organization=self.org,
            offering=self.offering,
            teacher=self.actor,
            kinds=["seminar"],
            source="legacy",
            batch="PRIVATE_SOURCE_BATCH",
        )
        share.enrollments.add(self.enrollment)
        through = JournalShare.enrollments.through.objects.get(journalshare=share, enrollment=self.enrollment)
        before = (
            list(JournalShare.objects.values()),
            list(JournalShare.enrollments.through.objects.values()),
            list(TeacherAssignment.objects.values()),
        )
        result = self.capture()
        data = result["data"]
        self.assertFalse(result["coverage"]["teacher_access_attested"])
        self.assertEqual(data["teachers"][0]["user_id"], self.actor.pk)
        self.assertTrue(data["teachers"][0]["is_current_owner"])
        self.assertTrue(data["teachers"][0]["has_positive_current_assignment"])
        self.assertTrue(data["teachers"][0]["grade_input_role_active"])
        self.assertEqual(data["shares"][0]["kinds"], ["seminar"])
        self.assertEqual(data["shares"][0]["source"], "legacy")
        self.assertEqual(data["share_links"][0]["link_id"], through.pk)
        self.assertEqual(data["share_links"][0]["enrollment_id"], str(self.enrollment.pk))
        self.assertEqual(data["assignments"][0]["id"], str(assignment.pk))
        self.assertEqual(
            before,
            (
                list(JournalShare.objects.values()),
                list(JournalShare.enrollments.through.objects.values()),
                list(TeacherAssignment.objects.values()),
            ),
        )
        encoded = json.dumps(result)
        for value in [
            "PRIVATE_GROUP_NOTE",
            "PRIVATE_FREE_NOTE",
            "PRIVATE_SOURCE_BATCH",
            '"permissions"',
            '"can_write"',
        ]:
            self.assertNotIn(value, encoded)
        with patch.object(spec, "MAX_SHARE_LINKS", 0):
            with self.assertRaises(SnapshotError):
                self.capture()
        with patch.object(spec, "MAX_TEACHERS", 0):
            with self.assertRaisesRegex(SnapshotError, "teacher_budget"):
                self.capture()

    def test_blocked_deleted_source_profile_preserved_not_filtered(self):
        UserProfile.objects.filter(user=self.student).update(
            is_deleted=True, blocked_at=timezone.now(), deleted_at=timezone.now()
        )
        result = self.capture()
        flag = next(r for r in result["data"]["profiles"] if r["user_id"] == self.student.pk)
        self.assertTrue(flag["is_deleted"])
        self.assertIsNotNone(flag["blocked_at"])
        self.assertIsNotNone(flag["deleted_at"])
        self.assertEqual(result["data"]["identity"][0]["target_user_id"], self.student.pk)
        self.assertTrue(UserProfile.objects.get(user=self.student).is_deleted)

    def test_foreign_profile_cannot_match_source_numeric_id(self):
        foreign = get_user_model().objects.create_user("outside-tenant-identity")
        org = make_org("outside-level-profile", owner=foreign)
        UserProfile.objects.filter(user=foreign).update(organization=org, institutional_identifier="2", fin=None)
        result = self.capture()
        self.assertIsNone(result["data"]["identity"][1]["target_user_id"])
        self.assertNotIn(foreign.pk, {r["user_id"] for r in result["data"]["profiles"]})

    def test_typed_ledger_contradiction_is_held_with_hashed_provenance(self):
        other = get_user_model().objects.create_user("contradictory-level-target")
        UserProfile.objects.filter(user=other).update(organization=self.org, institutional_identifier=None, fin=None)
        run = apps.get_model("legacy_import", "LegacyMigrationRun").objects.create(
            organization=self.org,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            schema_version="v1",
            transform_version="v1",
            mode="profile",
        )
        apps.get_model("legacy_import", "LegacyMigrationRun").objects.filter(pk=run.pk).update(
            status="running", started_at=timezone.now()
        )
        apps.get_model("legacy_import", "LegacyEntityMap").objects.create(
            organization=self.org,
            source_system="myedu_mariadb",
            entity_type="student",
            legacy_pk="1",
            source_row_hash="b" * 64,
            transform_version="v1",
            target_model_label="auth.user",
            target_pk=str(other.pk),
            created_run=run,
            state="migrated",
        )
        result = self.capture()
        identity = result["data"]["identity"][0]
        self.assertIsNone(identity["target_user_id"])
        self.assertIn("identity_evidence_contradiction", identity["reasons"])
        self.assertEqual(result["data"]["identity_ledger_proofs"][0]["target_user_id"], other.pk)
        self.assertEqual(
            len(result["data"]["identity_ledger_proofs"][0]["target_reference_sha256"]),
            64,
        )

    def test_unenrolled_same_tenant_profile_can_resolve_without_creating_account(self):
        new = get_user_model().objects.create_user("unenrolled-level-profile", is_active=False)
        UserProfile.objects.filter(user=new).update(
            organization=self.org,
            institutional_identifier="2",
            fin=None,
            access_state="staged",
        )
        before = get_user_model().objects.count()
        p = self.capture()
        self.assertEqual(p["data"]["identity"][1]["target_user_id"], new.pk)
        self.assertEqual(get_user_model().objects.count(), before)
        self.assertFalse(any(e["student_id"] == new.pk for e in p["data"]["enrollments"]))


@override_settings(RLS_TRANSACTION_SCOPED=False)
class EnglishEvidenceSessionRLS(EnglishEvidenceBase):
    pass


@override_settings(RLS_TRANSACTION_SCOPED=True)
class EnglishEvidenceTransactionRLS(EnglishEvidenceBase):
    pass
