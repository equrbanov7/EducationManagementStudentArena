"""İmtahan mərkəzi — apellyasiya statistikası endpointləri.

* İcazə: yalnız imtahan mərkəzi istifadəçisi — tələbə 403.
* Data: summary (ümumi/status), filtr (status, imtahan tipi), səhifələmə.
* Charts: status/tip/fənn/müəllim/aylıq aqreqatları.
* AI: API açarı olmadan fail-soft JSON (500 yox).
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.appeals.constants import APPEAL_STATUS_ACCEPTED, APPEAL_STATUS_PENDING, APPEAL_STATUS_REJECTED
from apps.appeals.models import Appeal
from apps.exams.models import Exam, ExamAttempt
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class AppealStatisticsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("aps_owner", "aps_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="APS University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.center = User.objects.create_user("aps_center", "aps_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center")
        cls.student = User.objects.create_user("aps_student", "aps_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")

        cls.final = Exam.objects.create(
            title="APS Final", author=cls.owner, organization=cls.org, exam_type="test", exam_type_extended="final"
        )
        cls.midterm = Exam.objects.create(
            title="APS Midterm",
            author=cls.owner,
            organization=cls.org,
            exam_type="written",
            exam_type_extended="midterm",
        )

        cls._appeal(cls.final, APPEAL_STATUS_PENDING, 1)
        cls._appeal(cls.final, APPEAL_STATUS_ACCEPTED, 2)
        cls._appeal(cls.midterm, APPEAL_STATUS_REJECTED, 3)

        cls.data_url = reverse("appeals:appeal_stats_data")
        cls.charts_url = reverse("appeals:appeal_stats_charts")
        cls.filters_url = reverse("appeals:appeal_stats_filters")
        cls.ai_url = reverse("appeals:appeal_stats_ai")

    @classmethod
    def _appeal(cls, exam, status, number):
        attempt = ExamAttempt.objects.create(user=cls.student, exam=exam, status="submitted", attempt_number=number)
        return Appeal.objects.create(
            attempt=attempt, exam=exam, student=cls.student, organization=cls.org, status=status
        )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_student_cannot_access(self):
        client = self._client(self.student)
        self.assertEqual(client.get(self.data_url).status_code, 403)
        self.assertEqual(client.get(self.charts_url).status_code, 403)
        self.assertEqual(client.get(self.ai_url).status_code, 403)

    def test_data_summary_and_rows(self):
        data = self._client(self.center).get(self.data_url).json()
        self.assertEqual(data["summary"]["total"], 3)
        self.assertEqual(data["summary"]["exams"], 2)
        by_status = {row["code"]: row["n"] for row in data["summary"]["by_status"]}
        self.assertEqual(by_status[APPEAL_STATUS_PENDING], 1)
        self.assertEqual(by_status[APPEAL_STATUS_ACCEPTED], 1)
        self.assertEqual(by_status[APPEAL_STATUS_REJECTED], 1)
        self.assertEqual(len(data["results"]), 3)
        self.assertIn("status_code", data["results"][0])

    def test_same_status_is_not_undercounted(self):
        # Regressiya: Appeal.Meta.ordering GROUP BY-a sızıb eyni statuslu
        # apellyasiyaları ayrı sayırdı. İkinci "accepted" → sayğac 2 olmalı.
        self._appeal(self.midterm, APPEAL_STATUS_ACCEPTED, 9)
        data = self._client(self.center).get(self.data_url).json()
        by_status = {row["code"]: row["n"] for row in data["summary"]["by_status"]}
        self.assertEqual(by_status[APPEAL_STATUS_ACCEPTED], 2)
        self.assertEqual(data["summary"]["total"], 4)

    def test_status_filter(self):
        data = self._client(self.center).get(self.data_url, {"status": APPEAL_STATUS_ACCEPTED}).json()
        self.assertEqual(data["summary"]["total"], 1)
        self.assertEqual(data["results"][0]["status_code"], APPEAL_STATUS_ACCEPTED)

    def test_exam_type_filter(self):
        data = self._client(self.center).get(self.data_url, {"type": "midterm"}).json()
        self.assertEqual(data["summary"]["total"], 1)
        self.assertEqual(data["results"][0]["exam"], "APS Midterm")

    def test_exam_format_filter(self):
        data = self._client(self.center).get(self.data_url, {"format": "written"}).json()
        self.assertEqual(data["summary"]["total"], 1)

    def test_charts_payload(self):
        data = self._client(self.center).get(self.charts_url).json()
        self.assertEqual(sum(data["by_status"]["counts"]), 3)
        self.assertEqual(sum(data["by_type"]["counts"]), 3)
        self.assertEqual(sum(data["monthly"]["counts"]), 3)
        self.assertIn("by_subject", data)
        self.assertIn("by_teacher", data)

    def test_filters_metadata(self):
        data = self._client(self.center).get(self.filters_url).json()
        self.assertTrue(any(s["value"] == "fall" for s in data["semesters"]))
        self.assertTrue(any(s["value"] == APPEAL_STATUS_PENDING for s in data["statuses"]))
        self.assertTrue(data["types"])
        self.assertTrue(data["formats"])

    @override_settings(GEMINI_API_KEY="")
    def test_ai_endpoint_fail_soft_without_api_key(self):
        response = self._client(self.center).get(self.ai_url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ok"])
