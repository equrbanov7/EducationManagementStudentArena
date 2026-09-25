"""Dözümlü axtarış (sahib 2026-09-26) — apellyasiya siyahıları və statistikası."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.appeals.constants import APPEAL_STATUS_PENDING
from apps.appeals.models import Appeal
from apps.appeals.selectors import filter_student_appeals, student_appeals_queryset
from apps.exams.models import Exam, ExamAttempt
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class AppealSearchTolerantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("aps26_owner", "aps26_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="APS26 Uni", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active", is_active=True
        )
        cls.center = User.objects.create_user("aps26_center", "aps26_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.aliyev = User.objects.create_user(
            "aps26_s1", "aps26_s1@test.az", PASSWORD, first_name="Şahzad", last_name="Əliyev"
        )
        _assign_user_to_org(cls.aliyev, cls.org, ProfileRole.STUDENT, "student")
        cls.other = User.objects.create_user(
            "aps26_s2", "aps26_s2@test.az", PASSWORD, first_name="Nigar", last_name="Məmmədova"
        )
        _assign_user_to_org(cls.other, cls.org, ProfileRole.STUDENT, "student")
        cls.db_exam = Exam.objects.create(
            title="Verilənlər bazası", author=cls.owner, organization=cls.org, exam_type="test"
        )
        cls.net_exam = Exam.objects.create(title="Şəbəkələr", author=cls.owner, organization=cls.org, exam_type="test")
        cls._appeal(cls.aliyev, cls.db_exam, 1)
        cls._appeal(cls.aliyev, cls.net_exam, 2)
        cls._appeal(cls.other, cls.net_exam, 3)

    @classmethod
    def _appeal(cls, student, exam, number):
        attempt = ExamAttempt.objects.create(user=student, exam=exam, status="submitted", attempt_number=number)
        return Appeal.objects.create(
            attempt=attempt, exam=exam, student=student, organization=cls.org, status=APPEAL_STATUS_PENDING
        )

    def test_student_list_exam_title_is_tolerant(self):
        base = student_appeals_queryset(self.aliyev)
        self.assertEqual(
            [a.exam_id for a in filter_student_appeals(base, search="Verilenler")],
            [self.db_exam.id],
        )
        self.assertEqual([a.exam_id for a in filter_student_appeals(base, search="sebekeler")], [self.net_exam.id])
        self.assertEqual(filter_student_appeals(base, search="").count(), 2)

    def test_center_statistics_student_name_is_tolerant(self):
        client = Client()
        client.force_login(self.center)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        url = reverse("appeals:appeal_stats_data")
        for query, expected in (("Aliyev", 2), ("Shahzad aliyev", 2), ("memmedova", 1), ("sebeke", 2)):
            with self.subTest(query=query):
                data = client.get(url, {"q": query}).json()
                self.assertEqual(data["summary"]["total"], expected)
