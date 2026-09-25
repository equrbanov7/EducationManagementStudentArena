"""Dözümlü axtarış (sahib 2026-09-26) — tapşırıq roster API-ləri və cavab süzgəci."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.http import QueryDict
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.assignments.models import Assignment, Submission
from apps.assignments.tests.test_views import _assign_user_to_org, _login_with_org
from apps.courses.models import Course, CourseMembership
from apps.organizations.models import Organization
from apps.task_submission_core.review import apply_submission_filters
from core.constants import OrganizationType

User = get_user_model()
_PASSWORD = "StrongPass123!"


class RosterSearchTolerantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("as26_owner", "as26_owner@example.com", _PASSWORD)
        cls.organization = Organization.objects.create(
            name="AS26 Org", org_type=OrganizationType.SCHOOL, owner=cls.owner, status="active", is_active=True
        )
        _assign_user_to_org(cls.owner, cls.organization, ProfileRole.TEACHER)
        cls.aliyev = User.objects.create_user(
            "as26_s1", "as26_s1@example.com", _PASSWORD, first_name="Şahzad", last_name="Əliyev"
        )
        cls.other = User.objects.create_user(
            "as26_s2", "as26_s2@example.com", _PASSWORD, first_name="Nigar", last_name="Kərimova"
        )
        for student in (cls.aliyev, cls.other):
            _assign_user_to_org(student, cls.organization, ProfileRole.STUDENT)
        cls.course = Course.objects.create(owner=cls.owner, title="AS26 Course", status="published")
        CourseMembership.objects.create(course=cls.course, user=cls.aliyev, role="student", group_name="234 K ing")
        CourseMembership.objects.create(course=cls.course, user=cls.other, role="student", group_name="701 biz")

    def setUp(self):
        self.client = Client()
        _login_with_org(self.client, self.owner, self.organization)

    def test_search_students_aliyev_and_shahzad(self):
        for query in ("Aliyev", "shahzad", "Şahzad Əliyev"):
            with self.subTest(query=query):
                response = self.client.get(
                    reverse("assignments:search_students"), {"course_id": self.course.id, "q": query}
                )
                self.assertEqual([row["id"] for row in response.json()["results"]], [self.aliyev.id])
        response = self.client.get(reverse("assignments:search_students"), {"course_id": self.course.id, "q": ""})
        self.assertEqual(len(response.json()["results"]), 2)

    def test_search_groups_is_compact(self):
        for query in ("234king", "234k ing", "234 K ing"):
            with self.subTest(query=query):
                response = self.client.get(
                    reverse("assignments:search_groups"), {"course_id": self.course.id, "q": query}
                )
                self.assertEqual([row["id"] for row in response.json()["results"]], ["234 K ing"])
        response = self.client.get(reverse("assignments:search_groups"), {"course_id": self.course.id, "q": ""})
        self.assertEqual(len(response.json()["results"]), 2)

    def test_submission_filter_student_name_and_content(self):
        assignment = Assignment.objects.create(
            course=self.course,
            title="AS26 Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        hit = Submission.objects.create(
            assignment=assignment, user=self.aliyev, content="Verilənlər bazası", status="submitted"
        )
        Submission.objects.create(assignment=assignment, user=self.other, content="Şəbəkə", status="submitted")
        base = assignment.submissions.all()

        def ids(query):
            submissions, _ = apply_submission_filters(
                base,
                QueryDict(f"q={query}"),
                student_lookup_prefix="user",
                allowed_status_filters={"all", "submitted"},
            )
            return [s.id for s in submissions]

        self.assertEqual(ids("Aliyev"), [hit.id])
        self.assertEqual(ids("verilenler"), [hit.id])
        self.assertEqual(len(ids("")), 2)
