"""«İmtahan statistikaları → Excel yüklə» — böyük ixrac worker-də (sahib 2026-11-17: «236 bio … download.htm»).

Prod-da süzgəcsiz ixrac 124 s sonra HTTP 500 (HTML) qaytarırdı — brauzer onu «download.htm» kimi endirirdi.
Kiçik dəst dərhal .xlsx, böyük dəst export job-a düşür; İmtahan Mərkəzi işçisi gözləmə / status / endirmə
səhifələrini açır (əvvəl yalnız müəllim).
"""

from __future__ import annotations

from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from openpyxl import load_workbook

from apps.exams.models import Exam, ExamAttempt, TextExtractionJob
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()


class ExamCenterStatsExportAsyncTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            owner = User.objects.create_user("esx_owner", "esx_owner@test.az", "pw")
            cls.org = Organization.objects.create(
                name="ESX Univ", slug="esx-univ", org_type=OrganizationType.UNIVERSITY, owner=owner,
                status="active", is_active=True,
            )  # fmt: skip
            cls.center = User.objects.create_user("esx_center", "esx_center@test.az", "pw")
            Membership.objects.create(
                user=cls.center, organization=cls.org, role=cls.org.roles.get(name="exam_center_head"),
                is_primary=True, is_active=True,
            )  # fmt: skip
            teacher = User.objects.create_user("esx_teacher", "esx_teacher@test.az", "pw")
            exam = Exam.objects.create(
                title="Biologiya 236 BİO", author=teacher, organization=cls.org, exam_type="test", is_active=True
            )
            for index in range(3):
                student = User.objects.create_user(f"esx_s{index}", f"esx_s{index}@test.az", "pw", first_name="Tələbə")
                ExamAttempt.objects.create(user=student, exam=exam, status="submitted")

    def _request(self, **params):
        request = RequestFactory().get(reverse("exams:exam_center_stats_export"), params)
        request.user = self.center
        request.organization = self.org
        request.session = SessionStore()
        request._messages = FallbackStorage(request)
        return request

    def _export(self, **params):
        from apps.exams.views.exam_center import statistics

        with mock.patch.object(statistics, "_stats_org", return_value=self.org):
            return statistics.exam_center_stats_export(self._request(**params))

    def test_small_export_is_immediate_xlsx(self):
        with bypass_rls():
            response = self._export(q="Tələbə")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Disposition"].startswith('attachment; filename="imtahan-statistika-'))
        rows = list(load_workbook(BytesIO(response.content)).active.iter_rows(values_only=True))
        self.assertEqual(len(rows), 4)  # başlıq + 3 cəhd

    @override_settings(EXPORT_SYNC_MAX_ROWS=1)
    def test_large_export_goes_to_worker_and_center_can_download(self):
        with bypass_rls(), mock.patch("apps.exams.tasks.run_export_job.delay") as delay:
            response = self._export(year="", sort="-date", bogus="x")
        self.assertEqual(response.status_code, 302)
        delay.assert_called_once()
        with bypass_rls():
            job = TextExtractionJob.objects.get(user=self.center)
            self.assertEqual(job.payload["export"], "exam_center_stats_xlsx")
            self.assertEqual(job.payload["params"]["filters"], {"sort": "-date"})  # naməlum açar atılır
        self.assertEqual(response["Location"], reverse("exams:export_job_waiting", kwargs={"job_id": job.pk}))

        from apps.exams.tasks import run_export_job

        run_export_job(str(job.pk))
        client = Client()
        client.force_login(self.center)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        self.assertEqual(client.get(response["Location"]).status_code, 200)  # əvvəl: yalnız müəllim → 403
        status = client.get(reverse("exams:text_extraction_status", kwargs={"job_id": job.pk}))
        self.assertEqual(status.json()["status"], "success")
        download = client.get(reverse("exams:export_job_download", kwargs={"job_id": job.pk}))
        self.assertEqual(download.status_code, 200)
        content = b"".join(download.streaming_content) if download.streaming else download.content
        self.assertTrue(content.startswith(b"PK"))
        rows = list(load_workbook(BytesIO(content)).active.iter_rows(values_only=True))
        self.assertEqual(len(rows), 4)

    def test_worker_builder_refuses_non_center_user(self):
        from apps.exams.export_registry import run_export

        stranger = User.objects.create_user("esx_x", "esx_x@test.az", "pw")
        with self.assertRaises(ValueError):
            run_export("exam_center_stats_xlsx", user=stranger, organization=self.org, params={"filters": {}})
