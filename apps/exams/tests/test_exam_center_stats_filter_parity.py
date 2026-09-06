"""İmtahan statistikası apellyasiya statistikası ilə eyni filtrləri təklif edir.

İstifadəçi şikayəti (2026-07-29): "birində 8-di, o birində 11" — imtahan
panelində İMTAHAN FORMASI, STATUS və SEMESTR filtrləri yox idi.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam, ExamAttempt
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class ExamCenterStatsFilterParityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ecfp_owner", "ecfp_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="ECFP University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.center = User.objects.create_user("ecfp_center", "ecfp_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")

        cls.student = User.objects.create_user("ecfp_student", "ecfp_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")

        cls.test_exam = Exam.objects.create(
            title="ECFP Test formalı",
            author=cls.owner,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
        )
        cls.written_exam = Exam.objects.create(
            title="ECFP Yazılı formalı",
            author=cls.owner,
            organization=cls.org,
            exam_type="written",
            exam_type_extended="final",
        )
        now = timezone.now()
        cls.submitted = ExamAttempt.objects.create(
            user=cls.student,
            exam=cls.test_exam,
            attempt_number=1,
            status="submitted",
            started_at=now,
            finished_at=now,
        )
        cls.expired = ExamAttempt.objects.create(
            user=cls.student,
            exam=cls.written_exam,
            attempt_number=2,
            status="expired",
            started_at=now,
            finished_at=now,
        )

    def setUp(self):
        self.client.force_login(self.center)

    def _rows(self, **params):
        response = self.client.get(reverse("exams:exam_center_stats_data"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_filters_endpoint_exposes_format_status_semester(self):
        response = self.client.get(reverse("exams:exam_center_stats_filters"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for key in ("formats", "statuses", "semesters"):
            with self.subTest(key=key):
                self.assertIn(key, payload, msg="apellyasiya paneli ilə paritet pozulub")
                self.assertTrue(payload[key], msg=f"{key} boşdur")

    def test_format_filter_narrows_results(self):
        written_only = self._rows(format="written")
        titles = str(written_only)
        self.assertIn("Yazılı", titles)
        self.assertNotIn("Test formalı", titles)

    def test_status_filter_narrows_results(self):
        expired_only = self._rows(status="expired")
        self.assertIn("Yazılı", str(expired_only))
        self.assertNotIn("Test formalı", str(expired_only))

    def test_unknown_status_is_ignored_not_applied(self):
        """Naməlum status queryset-i boşaltmamalıdır (fail-open deyil, ignore)."""
        everything = self._rows()
        with_garbage = self._rows(status="__nope__")
        self.assertEqual(str(with_garbage), str(everything))

    def test_semester_filter_uses_month_buckets(self):
        month = timezone.localtime(self.submitted.started_at).month
        bucket = "fall" if month in (9, 10, 11, 12, 1) else ("spring" if month in (2, 3, 4, 5, 6) else "summer")
        matching = self._rows(semester=bucket)
        self.assertIn("ECFP", str(matching))
