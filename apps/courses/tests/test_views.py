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
        self.other_teacher = User.objects.create_user(
            username="course_other_teacher",
            email="course_other_teacher@example.com",
            password="StrongPass123!",
        )
        self.external_student = User.objects.create_user(
            username="course_external_student",
            email="course_external_student@example.com",
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

        other_teacher_profile = self.other_teacher.profile
        other_teacher_profile.organization = self.org_a
        other_teacher_profile.organization_type = self.org_a.org_type
        other_teacher_profile.role = ProfileRole.TEACHER
        other_teacher_profile.save()

        external_student_profile = self.external_student.profile
        external_student_profile.organization = self.org_b
        external_student_profile.organization_type = self.org_b.org_type
        external_student_profile.role = ProfileRole.STUDENT
        external_student_profile.save()

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

    def test_course_dashboard_ignores_non_profile_referer_for_back_link(self):
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.get(
            reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id}),
            {"from_section": "assigned-courses"},
            HTTP_REFERER="/labs/1/some-internal-page/",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["profile_return_url"],
            f"{reverse('accounts:profile')}?section=assigned-courses",
        )

    def test_owner_can_update_course_status_from_dashboard(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        self.course_a.status = "draft"
        self.course_a.save(update_fields=["status"])

        next_url = f"{reverse('courses:course_dashboard', kwargs={'course_id': self.course_a.id})}?from_section=my-courses"
        response = self.client.post(
            reverse("courses:update_course_status", kwargs={"course_id": self.course_a.id}),
            {"status": "published", "next": next_url},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)
        self.course_a.refresh_from_db()
        self.assertEqual(self.course_a.status, "published")

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

    def test_edit_course_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("courses:edit_course", kwargs={"course_id": self.course_a.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_non_owner_teacher_gets_403_on_course_edit(self):
        self.client.force_login(self.other_teacher)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.get(reverse("courses:edit_course", kwargs={"course_id": self.course_a.id}))
        self.assertEqual(response.status_code, 403)

    def test_non_owner_teacher_cannot_add_or_remove_course_member(self):
        self.client.force_login(self.other_teacher)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        add_response = self.client.post(
            reverse("courses:add_member", kwargs={"course_id": self.course_a.id}),
            {"user_ids": [str(self.student.id)], "group_name": "A1"},
        )
        self.assertEqual(add_response.status_code, 403)

        member = CourseMembership.objects.get(course=self.course_a, user=self.student)
        delete_response = self.client.post(
            reverse("courses:delete_member", kwargs={"course_id": self.course_a.id, "member_id": member.id}),
        )
        self.assertEqual(delete_response.status_code, 403)
        self.assertTrue(CourseMembership.objects.filter(id=member.id).exists())

    def test_owner_cannot_add_cross_tenant_student(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.post(
            reverse("courses:add_member", kwargs={"course_id": self.course_a.id}),
            {"user_ids": [str(self.external_student.id)], "group_name": "A2"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CourseMembership.objects.filter(course=self.course_a, user=self.external_student).exists())
