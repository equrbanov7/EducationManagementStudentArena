"""
View tests for courses app.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class CourseOwnershipTenantFilteringTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="course_owner",
            email="course_owner@example.com",
            password="StrongPass123!",
        )
        self.student = User.objects.create_user(
            username="course_student",
            email="course_student@example.com",
            password="StrongPass123!",
        )

        self.org_a = Organization.objects.create(
            name="Course Org A",
            org_type=OrganizationType.SCHOOL,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.org_b = Organization.objects.create(
            name="Course Org B",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )

        owner_profile = self.owner.profile
        owner_profile.organization = self.org_a
        owner_profile.organization_type = self.org_a.org_type
        owner_profile.role = ProfileRole.TEACHER
        owner_profile.save()

        student_profile = self.student.profile
        student_profile.organization = self.org_a
        student_profile.organization_type = self.org_a.org_type
        student_profile.role = ProfileRole.STUDENT
        student_profile.save()

        self.course_a = Course.objects.create(
            owner=self.owner,
            title="Tenant A Course",
            status="published",
        )
        self.course_b = Course.objects.create(
            owner=self.owner,
            title="Tenant B Course",
            status="published",
            organization_id=999,
        )

        CourseMembership.objects.create(course=self.course_a, user=self.student, role="student")
        CourseMembership.objects.create(course=self.course_b, user=self.student, role="student")

        self.client.force_login(self.owner)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

    def test_my_courses_only_shows_owner_courses_in_active_tenant(self):
        response = self.client.get(reverse("courses:my_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course_a.title)
        self.assertNotContains(response, self.course_b.title)

    def test_student_courses_only_shows_assigned_courses_in_active_tenant(self):
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.get(reverse("courses:student_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course_a.title)
        self.assertNotContains(response, self.course_b.title)

    def test_course_dashboard_preserves_assigned_tasks_profile_return_context(self):
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.get(
            reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id}),
            {"from_section": "assigned-exams", "assigned_type": "labs"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["profile_return_section"], "assigned-exams")
        self.assertEqual(
            response.context["profile_return_url"],
            f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type=labs",
        )

    def test_course_dashboard_prefers_explicit_return_to_url(self):
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        return_to = f"{reverse('accounts:profile')}?section=courses"
        response = self.client.get(
            reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id}),
            {"from_section": "assigned-courses", "return_to": return_to},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["profile_return_url"], return_to)

    def test_delete_course_redirects_to_new_profile_page(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.post(
            reverse("courses:delete_course", kwargs={"course_id": self.course_a.id}),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('accounts:profile')}?section=my-courses")
        self.assertFalse(Course.objects.filter(id=self.course_a.id).exists())
