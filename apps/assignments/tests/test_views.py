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
from apps.organizations.models import Organization
from core.constants import OrganizationType

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


class AssignmentTenantIsolationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher_a = User.objects.create_user("assignment_tenant_teacher_a", "ta@example.com", "StrongPass123!")
        self.teacher_b = User.objects.create_user("assignment_tenant_teacher_b", "tb@example.com", "StrongPass123!")
        self.student_a = User.objects.create_user("assignment_tenant_student_a", "sa@example.com", "StrongPass123!")
        self.student_b = User.objects.create_user("assignment_tenant_student_b", "sb@example.com", "StrongPass123!")

        self.org_a = Organization.objects.create(
            name="Assignment Org A",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher_a,
            status="active",
            is_active=True,
        )
        self.org_b = Organization.objects.create(
            name="Assignment Org B",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher_b,
            status="active",
            is_active=True,
        )

        for user, org, role in (
            (self.teacher_a, self.org_a, ProfileRole.TEACHER),
            (self.teacher_b, self.org_b, ProfileRole.TEACHER),
            (self.student_a, self.org_a, ProfileRole.STUDENT),
            (self.student_b, self.org_b, ProfileRole.STUDENT),
        ):
            profile = user.profile
            profile.organization = org
            profile.organization_type = org.org_type
            profile.role = role
            profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

        self.course_a = Course.objects.create(owner=self.teacher_a, title="Assignment Course A", status="published")
        self.course_b = Course.objects.create(owner=self.teacher_b, title="Assignment Course B", status="published")

        self.assignment_b = Assignment.objects.create(
            course=self.course_b,
            title="Tenant B Assignment",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=1),
            status="published",
        )
        self.assignment_b.assigned_students.add(self.student_b)

        self.client.force_login(self.teacher_a)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

    def test_search_students_blocks_cross_tenant_course_id(self):
        response = self.client.get(
            reverse("assignments:search_students"),
            {"course_id": self.course_b.id, "q": "student"},
        )
        self.assertEqual(response.status_code, 404)

    def test_assignment_detail_blocks_cross_tenant_assignment_id(self):
        self.client.force_login(self.student_a)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.get(reverse("assignments:assignment_detail", kwargs={"pk": self.assignment_b.id}))
        self.assertEqual(response.status_code, 404)
