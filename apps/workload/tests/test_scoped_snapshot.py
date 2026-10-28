"""Real PostgreSQL, tenant/sentinel checks and authenticated encryption roundtrip."""

import base64
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TransactionTestCase

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from apps.organizations.models import Organization
from apps.workload.services.scoped_snapshot import SnapshotError, capture, encrypt
from apps.workload.services.scoped_snapshot.data import ORG
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()


class ScopedSnapshotTests(TransactionTestCase):
    def setUp(self):
        self.actor = User.objects.create_superuser("snapshot_operator", password="NO_AUTH_HASH_EXPORT")
        self.org = Organization.objects.create(
            id=ORG,
            name="Export scope",
            slug="snapshot-wcu",
            owner=self.actor,
            org_type="university",
            status="active",
            is_active=True,
        )
        self.stack = make_structure(self.org, code="SNAP")
        self.task = make_task(self.org, self.stack["chair"])
        self.row = make_row(self.task, self.stack, lecture_total=30, seminar_total=15)
        self.teacher = User.objects.create_user(
            "snapshot_teacher", first_name="Teacher", last_name="Example", password="PRIVATE_PASSWORD_SENTINEL"
        )
        activate_member(self.org, self.teacher, "snapshot_teacher", permissions=TEACHER_PERMS)
        self.teacher.profile.organization = self.org
        self.teacher.profile.patronymic = "Father"
        self.teacher.profile.phone = "CONTACT_SENTINEL"
        self.teacher.profile.save()
        self.foreign = make_org("foreign-snapshot")
        stack = make_structure(self.foreign, code="FOREIGN_PRIVATE_SENTINEL")
        task = make_task(self.foreign, stack["chair"])
        make_row(task, stack, lecture_total=99)

    def test_fixed_scope_allowlist_and_no_writes(self):
        with connection.execute_wrapper(self._deny_sensitive_auth_selection):
            snapshot = capture(self.actor.username)
        encoded = json.dumps(snapshot, default=str)
        self.assertEqual(snapshot["organization_id"], ORG)
        self.assertEqual([str(r["id"]) for r in snapshot["data"]["rows"]], [str(self.row.id)])
        for forbidden in [
            "FOREIGN_PRIVATE_SENTINEL",
            "CONTACT_SENTINEL",
            "PRIVATE_PASSWORD_SENTINEL",
            "password",
            "phone",
        ]:
            self.assertNotIn(forbidden, encoded)
        teacher = next(t for t in snapshot["data"]["teachers"] if t["id"] == self.teacher.id)
        self.assertEqual(teacher["patronymic"], "Father")
        self.assertEqual(self.task.rows.count(), 1)

    @staticmethod
    def _deny_sensitive_auth_selection(execute, sql, params, many, context):
        if 'FROM "auth_user"' in sql:
            assert '"password"' not in sql
        return execute(sql, params, many, context)

    def test_capture_requires_active_superuser_and_fresh_transaction(self):
        with self.assertRaisesRegex(SnapshotError, "active_superuser"):
            capture(self.teacher.username)
        from django.db import transaction

        with transaction.atomic(), self.assertRaisesRegex(SnapshotError, "fresh_postgresql"):
            capture(self.actor.username)

    def test_database_rejects_accidental_write_inside_collector(self):
        def bad_collect(**_kwargs):
            self.task.rows.update(lecture_total=999)

        with patch("apps.workload.services.scoped_snapshot.collect", side_effect=bad_collect):
            with self.assertRaises(Exception) as raised:
                capture(self.actor.username)
        self.assertIn("read-only", str(raised.exception))
        self.row.refresh_from_db()
        self.assertEqual(self.row.lecture_total, 30)

    def test_envelope_roundtrip_tamper_and_key_pin(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        pub = private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        import hashlib

        der = private.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        with patch("apps.workload.services.scoped_snapshot.KEY_FINGERPRINT", hashlib.sha256(der).hexdigest()):
            envelope = encrypt({"safe": "snapshot"}, pub)
        metadata = {k: envelope[k] for k in ["format", "cipher", "key_sha256"]}
        key = private.decrypt(
            base64.b64decode(envelope["wrapped_key"]),
            padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
        )
        cipher = base64.b64decode(envelope["ciphertext"])
        aad = json.dumps(metadata, sort_keys=True).encode()
        nonce = base64.b64decode(envelope["nonce"])
        self.assertEqual(json.loads(AESGCM(key).decrypt(nonce, cipher, aad)), {"safe": "snapshot"})
        with self.assertRaises(InvalidTag):
            AESGCM(key).decrypt(nonce, cipher[:-1] + bytes([cipher[-1] ^ 1]), aad)
        with self.assertRaisesRegex(SnapshotError, "fingerprint"):
            encrypt({}, pub)

    def test_command_never_overwrites_existing_snapshot_or_logs_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "snapshot.enc.json"
            public = Path(__file__).resolve().parents[3] / "scripts/data/wcu_workload_export_public.pem"
            log = StringIO()
            call_command(
                "export_wcu_workload_snapshot",
                actor=self.actor.username,
                public_key=str(public),
                output=str(output),
                stdout=log,
            )
            before = output.read_bytes()
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(self.teacher.username, log.getvalue())
            self.assertNotIn(b"snapshot_teacher", before)
            with self.assertRaises(CommandError):
                call_command(
                    "export_wcu_workload_snapshot",
                    actor=self.actor.username,
                    public_key=str(public),
                    output=str(output),
                    stdout=log,
                )
            self.assertEqual(output.read_bytes(), before)

    def test_counts_and_fingerprints_without_student_or_mark_records(self):
        from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark

        offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            period=self.stack["period"],
            group=self.stack["group"],
            instructor=self.teacher,
            lesson_hours=45,
        )
        student = User.objects.create_user("STUDENT_PRIVATE_SENTINEL")
        activate_member(self.org, student, "snapshot_student", permissions=["course.view"])
        student.profile.organization = self.org
        student.profile.save()
        enrollment = Enrollment.objects.create(organization=self.org, offering=offering, student=student)
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=offering,
            date="2026-10-20",
            kind="seminar",
            hours=2,
            instructor=self.teacher,
            topic="PRIVATE_TOPIC_SENTINEL",
        )
        mark = LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, status="present", score=7
        )
        snapshot = capture(self.actor.username)
        counts = snapshot["data"]["offering_counts"][0]
        self.assertEqual((counts["enrollments"], counts["lessons"], counts["marks"]), (1, 1, 1))
        encoded = json.dumps(snapshot, default=str)
        for sentinel in [student.username, str(mark.id), str(enrollment.id), "PRIVATE_TOPIC_SENTINEL"]:
            self.assertNotIn(sentinel, encoded)
        LessonMark.objects.filter(pk=mark.pk).update(score=9)
        after = capture(self.actor.username)["data"]["offering_counts"][0]
        self.assertNotEqual(counts["mark_state_md5"], after["mark_state_md5"])

    def test_collector_under_real_nonbypass_rls_role(self):
        from apps.workload.services.scoped_snapshot import collect as original

        def role_collect(**kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE rls_app_role")
                cursor.execute("SELECT rolbypassrls,rolsuper FROM pg_roles WHERE rolname=current_user")
                self.assertEqual(cursor.fetchone(), (False, False))
                cursor.execute(
                    "SELECT count(*) FROM workload_teachingtask WHERE organization_id=%s", [str(self.foreign.pk)]
                )
                self.assertEqual(cursor.fetchone()[0], 0)
            return original(**kwargs)

        with patch("apps.workload.services.scoped_snapshot.collect", side_effect=role_collect):
            snapshot = capture(self.actor.username)
        self.assertEqual(len(snapshot["data"]["tasks"]), 1)

    def test_student_sets_cross_group_overlap_and_foreign_exclusion(self):
        from apps.organizations.models import OrgUnit
        from apps.registrar.models import CourseOffering, Curriculum, Enrollment, StudentAcademicRecord
        from apps.workload.services.scoped_snapshot.roster_tokens import tokenize

        group = self.stack["group"]
        group.name = "233 KE"
        group.save(update_fields=["name"])
        alias = OrgUnit.objects.create(
            organization=self.org,
            parent=self.stack["specialty"],
            name="233 KE az",
            slug="snapshot-alias",
            unit_type="group",
        )
        english = OrgUnit.objects.create(
            organization=self.org,
            parent=self.stack["specialty"],
            name="233 KE ing",
            slug="snapshot-english",
            unit_type="group",
        )
        student = User.objects.create_user("SET_STUDENT_PRIVATE")
        activate_member(self.org, student, "set_student", permissions=["course.view"])
        student.profile.organization = self.org
        student.profile.save()
        curriculum = Curriculum.objects.create(
            organization=self.org, program=self.stack["program"], admission_year=2024
        )
        StudentAcademicRecord.objects.create(
            organization=self.org,
            student=student,
            program=self.stack["program"],
            curriculum=curriculum,
            group=group,
            admission_year=2024,
        )
        for target in [alias, english]:
            offering = CourseOffering.objects.create(
                organization=self.org, subject=self.stack["subject"], period=self.stack["period"], group=target
            )
            Enrollment.objects.create(organization=self.org, student=student, offering=offering)
        foreign_student = User.objects.create_user("FOREIGN_SET_PRIVATE")
        activate_member(self.foreign, foreign_student, "foreign_set_student", permissions=["course.view"])
        foreign_student.profile.organization = self.foreign
        foreign_student.profile.save()
        foreign_stack = make_structure(self.foreign, code="FOREIGNSET")
        foreign_curriculum = Curriculum.objects.create(
            organization=self.foreign, program=foreign_stack["program"], admission_year=2024
        )
        StudentAcademicRecord.objects.create(
            organization=self.foreign,
            student=foreign_student,
            program=foreign_stack["program"],
            curriculum=foreign_curriculum,
            group=foreign_stack["group"],
            admission_year=2024,
        )
        foreign_offering = CourseOffering.objects.create(
            organization=self.foreign,
            subject=foreign_stack["subject"],
            period=foreign_stack["period"],
            group=foreign_stack["group"],
        )
        Enrollment.objects.create(organization=self.foreign, student=foreign_student, offering=foreign_offering)
        secret = b"z" * 32
        with patch("apps.workload.services.scoped_snapshot.os.urandom", return_value=secret):
            snapshot = capture(self.actor.username)
        sar = snapshot["data"]["group_sar_students"]
        enrolled = snapshot["data"]["group_enrollment_students"]
        self.assertEqual(len(sar), 1)
        self.assertEqual({r["group_id"] for r in enrolled}, {alias.pk, english.pk})
        self.assertTrue(all(r["student_tokens"] == sar[0]["student_tokens"] for r in enrolled))
        foreign_token = tokenize(
            [{"group_id": group.pk, "status": "enrolled", "student_id": foreign_student.pk}],
            secret=secret,
            organization=ORG,
            group_fields=("group_id", "status"),
        )[0]["student_tokens"][0]
        encoded = json.dumps(snapshot, default=str)
        for forbidden in [student.username, foreign_student.username, foreign_token, '"student_id"']:
            self.assertNotIn(forbidden, encoded)
        self.assertNotIn(secret.decode(), encoded)
