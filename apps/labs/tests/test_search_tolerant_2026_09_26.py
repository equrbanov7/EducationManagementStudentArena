"""Dözümlü axtarış (sahib 2026-09-26) — laboratoriya cavabları siyahısının axtarışı."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.labs.models import Lab, LabAssignment, LabSubmission
from apps.labs.tests.test_views import _assign_user_to_org, _login_with_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()
_PASSWORD = "StrongPass123!"


class LabSubmissionsTolerantSearchTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("lab26_teacher", "lab26_teacher@example.com", _PASSWORD)
        cls.organization = Organization.objects.create(
            name="Lab26 Org", org_type=OrganizationType.SCHOOL, owner=cls.teacher, status="active", is_active=True
        )
        _assign_user_to_org(cls.teacher, cls.organization, ProfileRole.TEACHER)
        cls.aliyev = User.objects.create_user(
            "lab26_s1", "lab26_s1@example.com", _PASSWORD, first_name="Şahzad", last_name="Əliyev"
        )
        cls.other = User.objects.create_user(
            "lab26_s2", "lab26_s2@example.com", _PASSWORD, first_name="Nigar", last_name="Kərimova"
        )
        course = Course.objects.create(owner=cls.teacher, title="Lab26 Course", status="published")
        for student in (cls.aliyev, cls.other):
            _assign_user_to_org(student, cls.organization, ProfileRole.STUDENT)
            CourseMembership.objects.create(course=course, user=student, role="student")
        cls.lab = Lab.objects.create(
            course=course,
            title="Lab26",
            description="Lab26",
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(days=1),
            max_score=100,
            max_attempts=1,
            status="published",
            created_by=cls.teacher,
        )
        cls.hit = LabSubmission.objects.create(
            assignment=LabAssignment.get_or_create_for_student(cls.lab, cls.aliyev),
            status="submitted",
            attempt_number=1,
            submission_text="Verilənlər bazası hesabatı",
        )
        cls.miss = LabSubmission.objects.create(
            assignment=LabAssignment.get_or_create_for_student(cls.lab, cls.other),
            status="submitted",
            attempt_number=1,
            submission_text="Şəbəkə",
        )

    def test_name_and_text_queries_are_tolerant(self):
        _login_with_org(self.client, self.teacher, self.organization)
        url = reverse("labs:lab_submissions", kwargs={"pk": self.lab.id})
        for query in ("Aliyev", "shahzad", "verilenler", "Şahzad Əliyev"):
            with self.subTest(query=query):
                response = self.client.get(url, {"q": query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([s.id for s in response.context["submissions"]], [self.hit.id])
        response = self.client.get(url, {"q": ""})
        self.assertEqual(len(list(response.context["submissions"])), 2)
