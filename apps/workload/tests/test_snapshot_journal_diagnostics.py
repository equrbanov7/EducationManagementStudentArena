"""Real read-only capture, canonical gates, no sensitive auth projection."""

import json
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.registrar import gradebook
from apps.registrar.models import AssessmentScheme, CourseOffering, JournalShare
from apps.syllabus.models import Syllabus, SyllabusVersion
from apps.workload.services.scoped_snapshot import capture
from apps.workload.tests import test_scoped_snapshot as snapshot_fixtures
from apps.workload.tests.factories import TEACHER_PERMS, activate_member


class SnapshotJournalDiagnosticsTests(TransactionTestCase):
    setUp = snapshot_fixtures.ScopedSnapshotTests.setUp

    def offering(self):
        return CourseOffering.objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            period=self.stack["period"],
            group=self.stack["group"],
            instructor=self.teacher,
            lesson_hours=45,
        )

    @staticmethod
    def guard(execute, sql, params, many, context):
        # A JOIN may use auth_user.is_active; only SELECT projection is sensitive.
        projection = sql.split(" FROM ", 1)[0].lower()
        if sql.lstrip().upper().startswith("SELECT"):
            aliases = {"auth_user"} | set(re.findall(r'(?:FROM|JOIN) "auth_user" (T[0-9]+)', sql))
            for field in ("password", "email", "last_login", "personal_identifier", "phone"):
                for alias in aliases:
                    assert f'{alias.lower()}."{field}"' not in projection.replace('"auth_user"', "auth_user"), field
        return execute(sql, params, many, context)

    def diagnostic(self):
        with connection.execute_wrapper(self.guard):
            return capture(self.actor.username)["data"]["journal_access_diagnostics"]

    def test_missing_scheme_unknown_and_no_write_path(self):
        self.offering()
        with patch.object(gradebook, "ensure_assessment_scheme", side_effect=AssertionError("write helper forbidden")):
            result = self.diagnostic()[0]
        self.assertIsNone(result["journal_locked"])
        self.assertIsNone(result["structural_write_candidate"])
        self.assertFalse(result["runtime_write_verified"])
        self.assertIn("assessment_scheme_missing_no_creation_attempted", result["unknown_codes"])
        self.assertEqual(AssessmentScheme.objects.count(), 0)

    def test_existing_lock_matches_normal_path_without_auth_secrets(self):
        offering = self.offering()
        scheme = AssessmentScheme.objects.create(organization=self.org, offering=offering)
        for published, status in [(False, "draft"), (False, "chair_approved"), (True, "approved")]:
            scheme.is_published = published
            scheme.approval_status = status
            scheme.save()
            offering.refresh_from_db()
            expected = gradebook.journal_is_locked(offering)
            result = self.diagnostic()[0]
            self.assertEqual(result["journal_locked"], expected)
            self.assertEqual(result["structural_write_candidate"], not expected)
        self.assertEqual(AssessmentScheme.objects.count(), 1)

    def test_semesterless_approved_fallback_and_syllabus_gate(self):
        offering = self.offering()
        AssessmentScheme.objects.create(organization=self.org, offering=offering)
        syllabus = Syllabus.objects.create(
            organization=self.org, subject=offering.subject, author=self.teacher, chair_unit=self.stack["chair"]
        )
        version = SyllabusVersion.objects.create(
            organization=self.org,
            syllabus=syllabus,
            major=1,
            minor=0,
            status="approved",
            locked_at=timezone.now(),
            approved_by=self.actor,
        )
        self.org.settings = {"journal": {"require_approved_syllabus": True}}
        self.org.save()
        result = self.diagnostic()[0]
        self.assertEqual(result["syllabus_id"], str(syllabus.pk))
        self.assertEqual(result["approved_syllabus_version_id"], str(version.pk))
        self.assertTrue(result["syllabus_enforced"])
        self.assertFalse(result["syllabus_locked"])
        self.assertTrue(result["structural_write_candidate"])

    def test_share_scope_and_authority_revocation(self):
        offering = self.offering()
        AssessmentScheme.objects.create(organization=self.org, offering=offering)
        teacher = get_user_model().objects.create_user("share_diag", password="NEVER_PROJECT_PASSWORD")
        role = activate_member(self.org, teacher, "share_diag", permissions=TEACHER_PERMS)
        JournalShare.objects.create(organization=self.org, offering=offering, teacher=teacher, kinds=["seminar"])
        result = next(r for r in self.diagnostic() if r["teacher_id"] == teacher.pk)
        self.assertTrue(result["direct_editor"])
        self.assertTrue(result["share_kind_restricted"])
        self.assertFalse(result["share_full"])
        role.permissions = ["course.view"]
        role.save()
        result = next(r for r in self.diagnostic() if r["teacher_id"] == teacher.pk)
        self.assertFalse(result["direct_editor"])
        self.assertFalse(result["structural_write_candidate"])

    def test_nonbypass_readonly_capture_excludes_foreign_diagnostics(self):
        self.offering()
        from apps.workload.services.scoped_snapshot import collect as original

        def collect(**kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE rls_app_role")
                cursor.execute("SHOW transaction_read_only")
                self.assertEqual(cursor.fetchone()[0], "on")
                cursor.execute("SELECT rolbypassrls,rolsuper FROM pg_roles WHERE rolname=current_user")
                self.assertEqual(cursor.fetchone(), (False, False))
            return original(**kwargs)

        with patch("apps.workload.services.scoped_snapshot.collect", side_effect=collect):
            rows = self.diagnostic()
        self.assertEqual(len(rows), 1)
        encoded = json.dumps(rows)
        self.assertNotIn("FOREIGN_PRIVATE_SENTINEL", encoded)
        self.assertNotIn("PRIVATE_PASSWORD_SENTINEL", encoded)
