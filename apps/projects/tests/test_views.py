"""
View tests for projects app.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.courses.models import Course
from apps.projects.models import Project

User = get_user_model()


class ProjectDetailBackUrlTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("project_teacher", "project_teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("project_student", "project_student@example.com", "StrongPass123!")
        self.course = Course.objects.create(owner=self.teacher, title="Project Course", status="published")
        self.project = Project.objects.create(
            course=self.course,
            title="Project Back Url",
            description="Project back url test",
            start_date=timezone.now() - timedelta(days=1),
            deadline=timezone.now() + timedelta(days=2),
            status="active",
        )
        self.project.assigned_students.add(self.student)

    def test_project_detail_defaults_back_to_course_dashboard(self):
        self.client.login(username="project_student", password="StrongPass123!")
        response = self.client.get(reverse("projects:project_detail", kwargs={"pk": self.project.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["back_url"],
            reverse("courses:course_dashboard", kwargs={"course_id": self.course.id}),
        )

    def test_project_detail_returns_to_assigned_tasks_when_opened_from_profile_tasks(self):
        self.client.login(username="project_student", password="StrongPass123!")
        response = self.client.get(
            reverse("projects:project_detail", kwargs={"pk": self.project.id}),
            {"from_section": "assigned-exams", "assigned_type": "independent"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["back_url"],
            f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type=independent",
        )
