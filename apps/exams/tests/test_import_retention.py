"""Private visual-import bundle-ları üçün retention testləri."""

import os
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.exams.models import QuestionSubmission, TextExtractionJob
from apps.exams.services.import_retention import purge_expired_import_stashes
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class ImportRetentionTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name,
            EXAM_IMPORT_STASH_RETENTION_HOURS=48,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.user = User.objects.create_user("retention-owner", password="pw")
        self.organization = Organization.objects.create(
            name="Retention Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.user,
            status="active",
            is_active=True,
        )

    def _bundle(self, token, *, age_hours):
        prefix = f"question_imports/{token}"
        source_name = f"{prefix}/source.pdf"
        manifest_name = f"{prefix}/manifest.json"
        default_storage.save(source_name, ContentFile(b"%PDF"))
        default_storage.save(manifest_name, ContentFile(b"{}"))
        modified = (timezone.now() - timedelta(hours=age_hours)).timestamp()
        os.utime(default_storage.path(source_name), (modified, modified))
        os.utime(default_storage.path(manifest_name), (modified, modified))
        return manifest_name

    def test_purge_removes_only_expired_unreferenced_bundles(self):
        orphan = "a" * 32
        recent = "b" * 32
        submission_token = "c" * 32
        recent_job_token = "d" * 32
        old_job_token = "e" * 32
        names = {
            token: self._bundle(token, age_hours=72 if token != recent else 2)
            for token in (orphan, recent, submission_token, recent_job_token, old_job_token)
        }
        QuestionSubmission.objects.create(
            organization=self.organization,
            teacher=self.user,
            title="Pending visual import",
            subject="Math",
            group_label="G1",
            raw_text="1. source",
            import_token=submission_token,
        )
        recent_job = TextExtractionJob.objects.create(
            organization=self.organization,
            user=self.user,
            result_meta={"math_token": recent_job_token},
        )
        old_job = TextExtractionJob.objects.create(
            organization=self.organization,
            user=self.user,
            result_meta={"math_token": old_job_token},
        )
        TextExtractionJob.objects.filter(pk=old_job.pk).update(created_at=timezone.now() - timedelta(hours=72))

        purged = purge_expired_import_stashes()

        self.assertEqual(purged, 2)
        self.assertFalse(default_storage.exists(names[orphan]))
        self.assertFalse(default_storage.exists(names[old_job_token]))
        self.assertTrue(default_storage.exists(names[recent]))
        self.assertTrue(default_storage.exists(names[submission_token]))
        self.assertTrue(default_storage.exists(names[recent_job_token]))
        old_job.refresh_from_db()
        recent_job.refresh_from_db()
        self.assertNotIn("math_token", old_job.result_meta)
        self.assertIs(old_job.result_meta["visual_import_expired"], True)
        self.assertEqual(recent_job.result_meta["math_token"], recent_job_token)

    def test_stash_scan_reads_only_jobs_with_a_math_token(self):
        """Fon işi tutumu 2026-10-07: saatlıq süpürgə bütün iş cədvəlini Python-a yükləmir."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for _ in range(3):
            TextExtractionJob.objects.create(organization=self.organization, user=self.user, text="x" * 50)
        with CaptureQueriesContext(connection) as ctx:
            purge_expired_import_stashes()
        job_reads = [q["sql"] for q in ctx.captured_queries if 'FROM "exams_textextractionjob"' in q["sql"]]
        self.assertEqual(len(job_reads), 1)
        self.assertIn("math_token", job_reads[0])
        self.assertNotIn('"exams_textextractionjob"."text"', job_reads[0])


class ExtractionJobRetentionTests(TestCase):
    """Fon işi tutumu 2026-10-07: bitmiş işlər saxlama müddətindən sonra faylları ilə silinir."""

    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.user = User.objects.create_user("job-retention-owner", password="pw")
        self.organization = Organization.objects.create(
            name="Job Retention Org", org_type=OrganizationType.SCHOOL, owner=self.user, status="active", is_active=True
        )

    def _job(self, *, status, age_days, with_file=False):
        job = TextExtractionJob.objects.create(
            organization=self.organization, user=self.user, status=status, text="extracted", source_name="f.xlsx"
        )
        if with_file:
            job.result_file.save("export.xlsx", ContentFile(b"PK"), save=True)
        TextExtractionJob.objects.filter(pk=job.pk).update(created_at=timezone.now() - timedelta(days=age_days))
        return job

    def test_old_finished_jobs_and_their_files_are_removed(self):
        from apps.exams.tasks import purge_finished_extraction_jobs

        old_export = self._job(status=TextExtractionJob.STATUS_SUCCESS, age_days=30, with_file=True)
        old_failed = self._job(status=TextExtractionJob.STATUS_FAILED, age_days=30)
        recent = self._job(status=TextExtractionJob.STATUS_SUCCESS, age_days=2)
        stuck = self._job(status=TextExtractionJob.STATUS_PROCESSING, age_days=30)
        file_name = old_export.result_file.name
        self.assertTrue(default_storage.exists(file_name))

        self.assertEqual(purge_finished_extraction_jobs(), 2)

        remaining = set(TextExtractionJob.objects.values_list("pk", flat=True))
        self.assertEqual(remaining, {recent.pk, stuck.pk})
        self.assertNotIn(old_failed.pk, remaining)
        self.assertFalse(default_storage.exists(file_name), "export faylı da silinməlidir")

    @override_settings(EXAM_EXTRACTION_JOB_RETENTION_DAYS=0)
    def test_zero_retention_disables_purge(self):
        from apps.exams.services.import_retention import purge_finished_extraction_jobs

        self._job(status=TextExtractionJob.STATUS_SUCCESS, age_days=400)
        self.assertEqual(purge_finished_extraction_jobs(), 0)
        self.assertEqual(TextExtractionJob.objects.count(), 1)
