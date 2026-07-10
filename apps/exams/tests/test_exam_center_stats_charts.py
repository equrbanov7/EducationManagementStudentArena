"""İmtahan mərkəzi statistika qrafikləri + AI endpoint testləri.

* İcazə: yalnız imtahan mərkəzi istifadəçisi (superadmin daxil) — tələbə 403.
* Qrafik aqreqatları: paylanma, keçmə nisbəti, tip/ay üzrə saylar.
* AI endpointi API açarı olmadan fail-soft JSON qaytarır (500 yox).
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class ExamCenterStatsChartsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ecsc_owner", "ecsc_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="ECSC University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.center = User.objects.create_user("ecsc_center", "ecsc_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center")

        cls.student = User.objects.create_user("ecsc_student", "ecsc_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")

        cls.exam = Exam.objects.create(
            title="ECSC Final",
            author=cls.owner,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
        )
        # 80% (keçib) və 20% (kəsilib) — hər ikisi bitmiş, sınaq deyil.
        ExamAttempt.objects.create(
            user=cls.student, exam=cls.exam, status="submitted", correct_count=8, wrong_count=2, attempt_number=1
        )
        ExamAttempt.objects.create(
            user=cls.student, exam=cls.exam, status="submitted", correct_count=2, wrong_count=8, attempt_number=2
        )
        # Statistikaya düşməməli olanlar: sınaq cəhdi və yarımçıq cəhd.
        ExamAttempt.objects.create(
            user=cls.student,
            exam=cls.exam,
            status="submitted",
            correct_count=9,
            wrong_count=1,
            is_trial=True,
            attempt_number=3,
        )
        ExamAttempt.objects.create(
            user=cls.student, exam=cls.exam, status="in_progress", correct_count=5, wrong_count=5, attempt_number=4
        )

        cls.charts_url = reverse("exams:exam_center_stats_charts")
        cls.ai_url = reverse("exams:exam_center_stats_ai")

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_student_cannot_access(self):
        client = self._client(self.student)
        self.assertEqual(client.get(self.charts_url).status_code, 403)
        self.assertEqual(client.get(self.ai_url).status_code, 403)

    def test_charts_payload(self):
        client = self._client(self.center)
        response = client.get(self.charts_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["pass_fail"], {"threshold": 50, "pass": 1, "fail": 1})
        self.assertEqual(sum(data["distribution"]["counts"]), 2)
        self.assertEqual(len(data["distribution"]["labels"]), 10)
        # 80% → "80-89" zolağı, 20% → "20-29" zolağı
        self.assertEqual(data["distribution"]["counts"][8], 1)
        self.assertEqual(data["distribution"]["counts"][2], 1)
        self.assertEqual(data["avg_percent"], 50.0)

        self.assertEqual(data["by_type"]["counts"], [2])
        self.assertEqual(data["by_type"]["avg"], [50.0])
        self.assertEqual(data["monthly"]["counts"], [2])

    def test_charts_respect_type_filter(self):
        client = self._client(self.center)
        data = client.get(self.charts_url, {"type": "quiz"}).json()
        self.assertEqual(data["pass_fail"]["pass"] + data["pass_fail"]["fail"], 0)

    @override_settings(GEMINI_API_KEY="")
    def test_ai_endpoint_fail_soft_without_api_key(self):
        client = self._client(self.center)
        response = client.get(self.ai_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("error", data)

    def test_profile_section_renders_charts_block(self):
        """Bölmə şablonu qrafik konteynerini + AI düyməsini render edir."""
        client = self._client(self.center)
        response = client.get(reverse("accounts:profile"), {"section": "exam-center-stats"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("js-ecs-charts", content)
        self.assertIn("js-ecs-ai-btn", content)
        self.assertIn(self.charts_url, content)
        self.assertIn(self.ai_url, content)
        self.assertIn("exam_center_stats_charts.js", content)
