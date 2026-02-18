"""
View tests for exams app.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import StudentGroup
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class MyGroupsTenantIsolationTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher_groups",
            email="teacher_groups@example.com",
            password="StrongPass123!",
        )
        self.student_a = User.objects.create_user(
            username="student_a",
            email="student_a@example.com",
            password="StrongPass123!",
        )
        self.student_b = User.objects.create_user(
            username="student_b",
            email="student_b@example.com",
            password="StrongPass123!",
        )

        self.org_a = Organization.objects.create(
            name="Org A",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.org_b = Organization.objects.create(
            name="Org B",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )

        teacher_profile = self.teacher.profile
        teacher_profile.organization = self.org_a
        teacher_profile.organization_type = self.org_a.org_type
        teacher_profile.role = ProfileRole.TEACHER
        teacher_profile.save()

        student_a_profile = self.student_a.profile
        student_a_profile.organization = self.org_a
        student_a_profile.organization_type = self.org_a.org_type
        student_a_profile.role = ProfileRole.STUDENT
        student_a_profile.save()

        student_b_profile = self.student_b.profile
        student_b_profile.organization = self.org_b
        student_b_profile.organization_type = self.org_b.org_type
        student_b_profile.role = ProfileRole.STUDENT
        student_b_profile.save()

        self.client.login(username="teacher_groups", password="StrongPass123!")

    def _set_active_org(self, organization):
        profile = self.teacher.profile
        profile.organization = organization
        profile.organization_type = organization.org_type
        profile.save(update_fields=["organization", "organization_type", "updated_at"])

        session = self.client.session
        session["active_organization"] = organization.slug
        session.save()

    def test_my_groups_page_links_to_create_group_template(self):
        response = self.client.get(reverse("exams:teacher_group_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("exams:create_student_group"))

        create_response = self.client.get(reverse("exams:create_student_group"))
        self.assertEqual(create_response.status_code, 200)
        self.assertTemplateUsed(create_response, "exams/teacher/create_student_group.html")

    def test_groups_are_created_and_listed_per_active_tenant(self):
        self._set_active_org(self.org_a)
        response = self.client.post(
            reverse("exams:create_student_group"),
            {"name": "A Group", "students": [str(self.student_a.id)]},
        )
        self.assertEqual(response.status_code, 302)
        group_a = StudentGroup.objects.get(name="A Group")
        self.assertEqual(group_a.organization, self.org_a)

        self._set_active_org(self.org_b)
        response = self.client.post(
            reverse("exams:create_student_group"),
            {"name": "B Group", "students": [str(self.student_b.id)]},
        )
        self.assertEqual(response.status_code, 302)
        group_b = StudentGroup.objects.get(name="B Group")
        self.assertEqual(group_b.organization, self.org_b)

        self._set_active_org(self.org_a)
        response = self.client.get(reverse("exams:teacher_group_list"))
        self.assertContains(response, "A Group")
        self.assertNotContains(response, "B Group")

        self._set_active_org(self.org_b)
        response = self.client.get(reverse("exams:teacher_group_list"))
        self.assertContains(response, "B Group")
        self.assertNotContains(response, "A Group")

    def test_group_creation_rejects_cross_tenant_students(self):
        self._set_active_org(self.org_a)
        response = self.client.post(
            reverse("exams:create_student_group"),
            {"name": "Invalid Group", "students": [str(self.student_b.id)]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StudentGroup.objects.filter(name="Invalid Group").exists())
