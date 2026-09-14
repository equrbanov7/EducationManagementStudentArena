"""Perf auditi 2026-09-13 F-06 — `appeals:appeal_stats_data` sətir başına 2 sorğu
(`exam.allowed_groups.all()` + `items.count()`) atırdı → sorğu sayı apellyasiya
sayından asılı olmamalıdır, sətir məzmunu (qrup adları, bənd sayı) eyni qalmalıdır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.appeals.constants import APPEAL_STATUS_PENDING, APPEAL_TYPE_CHOICES
from apps.appeals.models import Appeal, AppealItem
from apps.exams.models import Exam, ExamAttempt, ExamQuestion, StudentGroup
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class AppealStatsRowsQueryBudgetTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("pf06_owner", "pf06_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="PF06 University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(cls.owner, cls.org, ProfileRole.TEACHER, "teacher")
        cls.center = User.objects.create_user("pf06_center", "pf06_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.student = User.objects.create_user("pf06_student", "pf06_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")
        cls.exam = Exam.objects.create(
            title="PF06 Final", author=cls.owner, organization=cls.org, exam_type="test", exam_type_extended="final"
        )
        cls.questions = [ExamQuestion.objects.create(exam=cls.exam, order=i + 1, text=f"S{i}") for i in range(3)]
        for name in ("PF06-A", "PF06-B"):
            group = StudentGroup.objects.create(teacher=cls.owner, organization=cls.org, name=name)
            cls.exam.allowed_groups.add(group)
        cls.data_url = reverse("appeals:appeal_stats_data")

    def _appeal(self, number: int, *, items: int):
        attempt = ExamAttempt.objects.create(
            user=self.student, exam=self.exam, status="submitted", attempt_number=number
        )
        appeal = Appeal.objects.create(
            attempt=attempt, exam=self.exam, student=self.student, organization=self.org, status=APPEAL_STATUS_PENDING
        )
        for index in range(items):
            AppealItem.objects.create(
                appeal=appeal,
                question=self.questions[index],
                appeal_type=APPEAL_TYPE_CHOICES[0][0],
                comment="Bu sualın cavabı yenidən yoxlanılmalıdır, çünki variantlar qarışıqdır.",
            )
        return appeal

    def _client(self):
        client = Client()
        client.force_login(self.center)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_query_count_is_independent_of_appeal_count(self):
        client = self._client()
        expected = {}
        for number in range(1, 3):
            expected[self._appeal(number, items=number).id] = number
        client.get(self.data_url)  # isinmə
        with CaptureQueriesContext(connection) as small:
            small_payload = client.get(self.data_url).json()
        self.assertEqual(len(small_payload["results"]), 2)

        for number in range(3, 11):
            expected[self._appeal(number, items=(number % 3) + 1).id] = (number % 3) + 1
        with CaptureQueriesContext(connection) as large:
            large_payload = client.get(self.data_url).json()
        self.assertEqual(len(large_payload["results"]), 10)
        self.assertEqual(
            len(small.captured_queries),
            len(large.captured_queries),
            "apellyasiya sayı artanda sorğu sayı artdı — sətir başına qrup/bənd sorğusu",
        )
        for row in large_payload["results"]:
            self.assertEqual(row["items"], expected[row["appeal_id"]])
            self.assertEqual(row["group"], "PF06-A, PF06-B")
        self.assertEqual(large_payload["summary"]["total"], 10)
        self.assertEqual(large_payload["pagination"]["count"], 10)
