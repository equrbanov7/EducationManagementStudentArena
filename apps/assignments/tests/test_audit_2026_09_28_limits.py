"""Audit 2026-09-28 SA-10 — ``max_attempts`` / ``max_score`` rəqəm deyilsə 400 JSON (500 yox)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.assignments.models import Assignment
from apps.assignments.tests.test_views import _assign_user_to_org, _login_with_org
from apps.courses.models import Course
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()
_PASSWORD = "StrongPass123!"


class AssignmentNumericLimitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sa10_owner", "sa10_owner@example.com", _PASSWORD)
        cls.organization = Organization.objects.create(
            name="SA10 Org", org_type=OrganizationType.SCHOOL, owner=cls.owner, status="active", is_active=True
        )
        _assign_user_to_org(cls.owner, cls.organization, ProfileRole.TEACHER)
        cls.course = Course.objects.create(owner=cls.owner, title="SA10 Course", status="published")

    def setUp(self):
        self.client = Client()
        _login_with_org(self.client, self.owner, self.organization)
        now = timezone.now().replace(second=0, microsecond=0)
        self.assignment = Assignment.objects.create(
            course=self.course,
            title="SA10",
            start_date=now - timedelta(days=1),
            due_date=now + timedelta(days=3),
            status="active",
            max_score=50,
            max_attempts=2,
        )

    def _create(self, **extra):
        payload = {
            "title": "Limits",
            "start_date": "2026-10-01T10:00",
            "deadline": "2026-10-05T10:00",
            "status": "active",
        }
        payload.update(extra)
        return self.client.post(reverse("assignments:create_assignment", args=[self.course.id]), payload)

    def test_non_numeric_values_on_create_return_400(self):
        for extra in ({"max_attempts": "abc"}, {"max_score": "yüz"}, {"max_attempts": "0"}, {"max_score": "-5"}):
            with self.subTest(extra=extra):
                response = self._create(**extra)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["success"])
        self.assertFalse(Assignment.objects.filter(title="Limits").exists())

    def test_valid_and_default_values_on_create(self):
        response = self._create(max_attempts="3", max_score="75,5")
        self.assertTrue(response.json()["success"], response.content[:300])
        created = Assignment.objects.get(id=response.json()["assignment_id"])
        self.assertEqual(created.max_attempts, 3)
        self.assertEqual(float(created.max_score), 75.5)

        default = Assignment.objects.get(id=self._create(title="Defaults").json()["assignment_id"])
        self.assertEqual(default.max_attempts, 1)
        self.assertEqual(float(default.max_score), 100.0)

    def test_non_numeric_value_on_edit_returns_400_and_keeps_row(self):
        url = reverse("assignments:edit_assignment", args=[self.assignment.id])
        response = self.client.post(
            url,
            {
                "title": "Changed",
                "start_date": "2026-10-01T10:00",
                "deadline": "2026-10-05T10:00",
                "max_attempts": "many",
                "status": "active",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.title, "SA10")
        self.assertEqual(self.assignment.max_attempts, 2)
        self.assertEqual(float(self.assignment.max_score), 50.0)
