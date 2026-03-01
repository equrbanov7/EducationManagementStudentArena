"""
View tests for labs app.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.courses.models import Course
from apps.labs.models import Lab

User = get_user_model()


class LabDetailBackUrlTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("lab_teacher", "lab_teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("lab_student", "lab_student@example.com", "StrongPass123!")
        self.course = Course.objects.create(owner=self.teacher, title="Lab Course", status="published")
        self.lab = Lab.objects.create(
            course=self.course,
            title="Lab Back Url",
            description="Lab back url test",
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(days=1),
            max_score=100,
            max_attempts=1,
            status="published",
            created_by=self.teacher,
        )

    def test_lab_detail_defaults_back_to_course_dashboard(self):
        self.client.login(username="lab_student", password="StrongPass123!")
        response = self.client.get(reverse("labs:lab_detail", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["back_url"],
            reverse("courses:course_dashboard", kwargs={"course_id": self.course.id}),
        )

    def test_lab_detail_returns_to_assigned_tasks_when_opened_from_profile_tasks(self):
        self.client.login(username="lab_student", password="StrongPass123!")
        response = self.client.get(
            reverse("labs:lab_detail", kwargs={"pk": self.lab.id}),
            {"from_section": "assigned-exams", "assigned_type": "labs"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["back_url"],
            f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type=labs",
        )
