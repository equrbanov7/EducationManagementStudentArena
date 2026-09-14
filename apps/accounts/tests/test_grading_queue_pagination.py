"""Qiymətləndirmə növbəsinin səhifələnməsi (audit 2026-09-10 P1-10).

Əvvəl ``grading_queue`` queryset-i şablona Paginator-suz verirdi — müəllimin
bütün kurslarındakı BÜTÜN gözləyən təhvillər bir səhifədə render olunurdu və
``submissions.count()`` ayrıca COUNT + tam SELECT edirdi. İndi 25-lik
səhifələr var, say ``paginator.count``-dan gəlir, kurs/tapşırıq süzgəcləri
səhifə linklərində saxlanılır.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

ROW_MARKER = '<tr data-submission-id="'


def _assign_user_to_org(user, organization, profile_role, *, membership_role_name):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={
            "role": organization.roles.get(name=membership_role_name),
            "is_primary": True,
            "is_active": True,
        },
    )


class GradingQueuePaginationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("gqp_teacher", "gqp_teacher@x.test", "pw12345678")
        cls.org = Organization.objects.create(
            name="GQP Org",
            slug="gqp-org",
            org_type=OrganizationType.SCHOOL,
            owner=cls.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, membership_role_name="teacher")

        now = timezone.now()
        cls.course_a = Course.objects.create(owner=cls.teacher, title="GQP kurs A", status="published")
        cls.course_b = Course.objects.create(owner=cls.teacher, title="GQP kurs B", status="published")
        cls.assignment_a = Assignment.objects.create(
            course=cls.course_a,
            title="GQP tapşırıq A",
            start_date=now - timedelta(days=1),
            due_date=now + timedelta(days=2),
            status="published",
            max_score=100,
        )
        cls.assignment_b = Assignment.objects.create(
            course=cls.course_b,
            title="GQP tapşırıq B",
            start_date=now - timedelta(days=1),
            due_date=now + timedelta(days=2),
            status="published",
            max_score=100,
        )
        for index in range(30):
            student = User.objects.create_user(f"gqp_student_{index}", f"gqp_student_{index}@x.test", "pw12345678")
            _assign_user_to_org(student, cls.org, ProfileRole.STUDENT, membership_role_name="student")
            Submission.objects.create(
                assignment=cls.assignment_a, user=student, content=f"Cavab A {index}", status="submitted"
            )
        for index in range(3):
            student = User.objects.create_user(f"gqp_student_b{index}", f"gqp_student_b{index}@x.test", "pw12345678")
            _assign_user_to_org(student, cls.org, ProfileRole.STUDENT, membership_role_name="student")
            Submission.objects.create(
                assignment=cls.assignment_b, user=student, content=f"Cavab B {index}", status="submitted"
            )

    def _client(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_first_page_renders_25_rows_and_true_total(self):
        client = self._client()
        url = reverse("accounts:grading_queue")
        client.get(url)  # isti-tut
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_pending"], 33)
        page_obj = response.context["page_obj"]
        self.assertEqual(page_obj.number, 1)
        self.assertEqual(page_obj.paginator.per_page, 25)
        self.assertEqual(page_obj.paginator.num_pages, 2)
        self.assertEqual(page_obj.paginator.count, 33)
        self.assertEqual(len(response.context["submissions"]), 25)
        self.assertEqual(response.content.decode().count(ROW_MARKER), 25)
        self.assertContains(response, "?page=2")
        # Səhifə SELECT-i LIMIT-lidir; count ayrıca COUNT-dur — tam dəst iki dəfə oxunmur.
        page_selects = [q["sql"] for q in ctx.captured_queries if "assignments_submission" in q["sql"]]
        self.assertTrue(any("LIMIT 25" in sql for sql in page_selects), page_selects)
        self.assertFalse(
            any("assignments_submission" in sql and "LIMIT" not in sql and "COUNT" not in sql for sql in page_selects),
            page_selects,
        )

    def test_second_page_has_remaining_rows(self):
        response = self._client().get(reverse("accounts:grading_queue"), {"page": "2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(len(response.context["submissions"]), 8)
        self.assertEqual(response.content.decode().count(ROW_MARKER), 8)
        self.assertEqual(response.context["total_pending"], 33)

    def test_out_of_range_page_falls_back_to_last_page(self):
        response = self._client().get(reverse("accounts:grading_queue"), {"page": "99"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)

    def test_filters_are_preserved_in_page_links(self):
        client = self._client()
        response = client.get(
            reverse("accounts:grading_queue"),
            {"course": str(self.course_a.id), "assignment": str(self.assignment_a.id)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_pending"], 30)
        self.assertEqual(len(response.context["submissions"]), 25)
        # Paylaşılan partial: `extra_query` autoescape ilə (`&amp;`), ayırıcı `&` literaldır.
        self.assertContains(response, f"?course={self.course_a.id}&amp;assignment={self.assignment_a.id}&page=2")

        second = client.get(
            reverse("accounts:grading_queue"),
            {"course": str(self.course_a.id), "assignment": str(self.assignment_a.id), "page": "2"},
        )
        self.assertEqual(len(second.context["submissions"]), 5)
        self.assertEqual(second.context["total_pending"], 30)
        self.assertNotContains(second, "Cavab B ")
        self.assertContains(second, f"?course={self.course_a.id}&amp;assignment={self.assignment_a.id}&page=1")

    def test_small_queue_has_no_pager(self):
        client = self._client()
        response = client.get(reverse("accounts:grading_queue"), {"course": str(self.course_b.id)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_pending"], 3)
        self.assertEqual(response.content.decode().count(ROW_MARKER), 3)
        self.assertNotContains(response, 'class="pagination"')
