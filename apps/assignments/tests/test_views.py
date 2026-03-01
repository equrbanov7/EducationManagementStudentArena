"""
View tests for assignments app.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.assignments.models import Assignment
from apps.courses.models import Course

User = get_user_model()


class AssignmentDetailBackUrlTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("assignment_teacher", "teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("assignment_student", "student@example.com", "StrongPass123!")

        self.student.profile.role = ProfileRole.STUDENT
        self.student.profile.save(update_fields=["role", "updated_at"])

        self.course = Course.objects.create(owner=self.teacher, title="Back Nav Course", status="published")
        self.assignment = Assignment.objects.create(
            course=self.course,
            title="Back Nav Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
        )
        self.assignment.assigned_students.add(self.student)

    def test_assignment_detail_defaults_back_to_course_dashboard(self):
        self.client.login(username="assignment_student", password="StrongPass123!")
        response = self.client.get(reverse("assignments:assignment_detail", kwargs={"pk": self.assignment.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["back_url"],
            reverse("courses:course_dashboard", kwargs={"course_id": self.course.id}),
        )

    def test_assignment_detail_returns_to_assigned_tasks_when_source_is_profile_tasks(self):
        self.client.login(username="assignment_student", password="StrongPass123!")
        response = self.client.get(
            reverse("assignments:assignment_detail", kwargs={"pk": self.assignment.id}),
            {"from_section": "assigned-exams", "assigned_type": "assignments"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["back_url"],
            f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type=assignments",
        )
