"""
View tests for exams app.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.exams.models import Exam, StudentGroup
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class MyGroupsTenantIsolationTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("teacher_groups", "teacher_groups@example.com", "StrongPass123!")
        self.teacher_a2 = User.objects.create_user("teacher_a2", "teacher_a2@example.com", "StrongPass123!")
        self.teacher_a3 = User.objects.create_user("teacher_a3", "teacher_a3@example.com", "StrongPass123!")
        self.teacher_a4 = User.objects.create_user("teacher_a4", "teacher_a4@example.com", "StrongPass123!")
        self.teacher_b = User.objects.create_user("teacher_b", "teacher_b@example.com", "StrongPass123!")
        self.student_a = User.objects.create_user("student_a", "student_a@example.com", "StrongPass123!")
        self.student_b = User.objects.create_user("student_b", "student_b@example.com", "StrongPass123!")
        self.member_a = User.objects.create_user("member_a", "member_a@example.com", "StrongPass123!")
        self.org_admin_a = User.objects.create_user("org_admin_a", "org_admin_a@example.com", "StrongPass123!")
        self.superadmin = User.objects.create_superuser("superadmin_groups", "superadmin_groups@example.com", "StrongPass123!")

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
            owner=self.teacher_b,
            status="active",
            is_active=True,
        )

        self._assign_profile(self.teacher, self.org_a, ProfileRole.TEACHER)
        self._assign_profile(self.teacher_a2, self.org_a, ProfileRole.TEACHER)
        self._assign_profile(self.teacher_a3, self.org_a, ProfileRole.TEACHER)
        self._assign_profile(self.teacher_a4, self.org_a, ProfileRole.TEACHER)
        self._assign_profile(self.teacher_b, self.org_b, ProfileRole.TEACHER)
        self._assign_profile(self.student_a, self.org_a, ProfileRole.STUDENT)
        self._assign_profile(self.student_b, self.org_b, ProfileRole.STUDENT)
        self._assign_profile(self.member_a, self.org_a, ProfileRole.MEMBER)
        self._assign_profile(self.org_admin_a, self.org_a, ProfileRole.ORG_ADMIN)
        self._assign_profile(self.superadmin, self.org_a, ProfileRole.SUPERADMIN)

        self._login_as(self.teacher)
        self._set_active_org(self.org_a)

    def _assign_profile(self, user, organization, role):
        profile = user.profile
        profile.organization = organization
        profile.organization_type = organization.org_type
        profile.role = role
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

    def _login_as(self, user):
        self.client.force_login(user)

    def _set_active_org(self, organization):
        session = self.client.session
        session["active_organization"] = organization.slug
        session.save()

    def _group_payload(self, **overrides):
        payload = {
            "name": "Test Group",
            "students": [str(self.student_a.id)],
            "primary_teacher": str(self.teacher.id),
            "assigned_teachers": [str(self.teacher.id)],
        }
        payload.update(overrides)
        return payload

    def test_my_groups_page_links_to_create_group_template(self):
        response = self.client.get(reverse("exams:teacher_group_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("exams:create_student_group"))

        create_response = self.client.get(reverse("exams:create_student_group"))
        self.assertEqual(create_response.status_code, 200)
        self.assertTemplateUsed(create_response, "exams/teacher/create_student_group.html")
        self.assertContains(create_response, reverse("exams:teacher_create_group"))

    def test_groups_are_created_and_listed_per_active_tenant(self):
        self._login_as(self.teacher)
        self._set_active_org(self.org_a)
        response = self.client.post(
            reverse("exams:teacher_create_group"),
            self._group_payload(name="A Group", primary_teacher=str(self.teacher.id), assigned_teachers=[str(self.teacher.id)]),
        )
        self.assertEqual(response.status_code, 302)
        group_a = StudentGroup.objects.get(name="A Group")
        self.assertEqual(group_a.organization, self.org_a)
        self.assertEqual(group_a.teacher, self.teacher)

        self._login_as(self.teacher_b)
        self._set_active_org(self.org_b)
        response = self.client.post(
            reverse("exams:teacher_create_group"),
            {
                "name": "B Group",
                "students": [str(self.student_b.id)],
                "primary_teacher": str(self.teacher_b.id),
                "assigned_teachers": [str(self.teacher_b.id)],
            },
        )
        self.assertEqual(response.status_code, 302)
        group_b = StudentGroup.objects.get(name="B Group")
        self.assertEqual(group_b.organization, self.org_b)
        self.assertEqual(group_b.teacher, self.teacher_b)

        self._login_as(self.teacher)
        self._set_active_org(self.org_a)
        response = self.client.get(reverse("exams:teacher_group_list"))
        self.assertContains(response, "A Group")
        self.assertNotContains(response, "B Group")

        self._login_as(self.teacher_b)
        self._set_active_org(self.org_b)
        response = self.client.get(reverse("exams:teacher_group_list"))
        self.assertContains(response, "B Group")
        self.assertNotContains(response, "A Group")

    def test_group_creation_rejects_cross_tenant_students(self):
        self._set_active_org(self.org_a)
        response = self.client.post(
            reverse("exams:teacher_create_group"),
            self._group_payload(name="Invalid Group", students=[str(self.student_b.id)]),
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StudentGroup.objects.filter(name="Invalid Group").exists())

    def test_group_list_contains_edit_and_delete_routes(self):
        self._set_active_org(self.org_a)
        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org_a, name="Route Group")
        group.students.add(self.student_a)
        group.teachers.add(self.teacher)

        response = self.client.get(reverse("exams:teacher_group_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("exams:teacher_update_group", args=[0]))
        self.assertContains(response, reverse("exams:teacher_delete_group", args=[group.id]))

    def test_student_cannot_access_group_management_routes(self):
        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org_a, name="Protected Group")
        group.students.add(self.student_a)
        group.teachers.add(self.teacher)

        self._login_as(self.student_a)
        self._set_active_org(self.org_a)

        self.assertEqual(self.client.get(reverse("exams:teacher_group_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("exams:create_student_group")).status_code, 403)
        self.assertEqual(self.client.post(reverse("exams:teacher_create_group"), self._group_payload(name="Blocked")).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("exams:teacher_update_group", args=[group.id]), self._group_payload(name="Blocked Update")).status_code,
            403,
        )
        self.assertEqual(self.client.post(reverse("exams:teacher_delete_group", args=[group.id])).status_code, 403)

    def test_teacher_can_multi_assign_teachers(self):
        self._login_as(self.teacher)
        self._set_active_org(self.org_a)
        response = self.client.post(
            reverse("exams:teacher_create_group"),
            self._group_payload(
                name="Teacher Multi Allowed",
                primary_teacher=str(self.teacher.id),
                assigned_teachers=[str(self.teacher.id), str(self.teacher_a2.id)],
            ),
        )
        self.assertEqual(response.status_code, 302)
        group = StudentGroup.objects.get(name="Teacher Multi Allowed")
        self.assertSetEqual(set(group.teachers.values_list("id", flat=True)), {self.teacher.id, self.teacher_a2.id})

    def test_org_admin_can_access_teacher_groups_url_and_multi_assign(self):
        self._login_as(self.org_admin_a)
        self._set_active_org(self.org_a)
        response = self.client.get(reverse("exams:teacher_group_list"))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("exams:teacher_create_group"),
            self._group_payload(
                name="Admin Group",
                primary_teacher=str(self.teacher.id),
                assigned_teachers=[str(self.teacher.id), str(self.teacher_a2.id)],
            ),
        )
        self.assertEqual(response.status_code, 302)
        group = StudentGroup.objects.get(name="Admin Group")
        self.assertEqual(group.organization, self.org_a)
        self.assertEqual(group.teacher, self.teacher)
        self.assertSetEqual(set(group.teachers.values_list("id", flat=True)), {self.teacher.id, self.teacher_a2.id})

    def test_org_admin_cannot_assign_more_than_three_teachers(self):
        self._login_as(self.org_admin_a)
        self._set_active_org(self.org_a)
        response = self.client.post(
            reverse("exams:teacher_create_group"),
            self._group_payload(
                name="Too Many Teachers",
                primary_teacher=str(self.teacher.id),
                assigned_teachers=[
                    str(self.teacher.id),
                    str(self.teacher_a2.id),
                    str(self.teacher_a3.id),
                    str(self.teacher_a4.id),
                ],
            ),
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StudentGroup.objects.filter(name="Too Many Teachers").exists())

    def test_org_admin_cannot_assign_cross_tenant_teachers(self):
        self._login_as(self.org_admin_a)
        self._set_active_org(self.org_a)
        response = self.client.post(
            reverse("exams:teacher_create_group"),
            self._group_payload(
                name="Cross Tenant Teacher Block",
                primary_teacher=str(self.teacher_b.id),
                assigned_teachers=[str(self.teacher_b.id)],
            ),
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StudentGroup.objects.filter(name="Cross Tenant Teacher Block").exists())

    def test_non_student_member_can_create_group_with_single_teacher(self):
        self._login_as(self.member_a)
        self._set_active_org(self.org_a)
        response = self.client.post(
            reverse("exams:teacher_create_group"),
            self._group_payload(
                name="Member Created Group",
                primary_teacher=str(self.teacher.id),
                assigned_teachers=[str(self.teacher.id), str(self.teacher_a2.id)],
            ),
        )
        self.assertEqual(response.status_code, 302)
        group = StudentGroup.objects.get(name="Member Created Group")
        self.assertEqual(group.teacher, self.teacher)
        # Bu rol multi assignment edə bilmədiyi üçün yalnız primary saxlanmalıdır.
        self.assertSetEqual(set(group.teachers.values_list("id", flat=True)), {self.teacher.id})

    def test_update_and_delete_routes_are_tenant_scoped(self):
        group_b = StudentGroup.objects.create(teacher=self.teacher_b, organization=self.org_b, name="OrgB Group")
        group_b.students.add(self.student_b)
        group_b.teachers.add(self.teacher_b)

        self._login_as(self.teacher)
        self._set_active_org(self.org_a)
        update_response = self.client.post(
            reverse("exams:teacher_update_group", args=[group_b.id]),
            self._group_payload(name="Should Not Update"),
        )
        delete_response = self.client.post(reverse("exams:teacher_delete_group", args=[group_b.id]))

        self.assertEqual(update_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        self.assertTrue(StudentGroup.objects.filter(id=group_b.id).exists())

    def test_non_superadmin_cannot_switch_session_to_other_tenant(self):
        self._login_as(self.teacher)
        self._set_active_org(self.org_b)
        response = self.client.get(reverse("exams:teacher_group_list"))
        self.assertEqual(response.status_code, 403)

    def test_superadmin_can_manage_any_active_tenant(self):
        self._login_as(self.superadmin)

        self._set_active_org(self.org_a)
        response_a = self.client.post(
            reverse("exams:teacher_create_group"),
            self._group_payload(
                name="Super A",
                students=[str(self.student_a.id)],
                primary_teacher=str(self.teacher.id),
                assigned_teachers=[str(self.teacher.id), str(self.teacher_a2.id)],
            ),
        )
        self.assertEqual(response_a.status_code, 302)

        self._set_active_org(self.org_b)
        response_b = self.client.post(
            reverse("exams:teacher_create_group"),
            {
                "name": "Super B",
                "students": [str(self.student_b.id)],
                "primary_teacher": str(self.teacher_b.id),
                "assigned_teachers": [str(self.teacher_b.id)],
            },
        )
        self.assertEqual(response_b.status_code, 302)

        self.assertTrue(StudentGroup.objects.filter(name="Super A", organization=self.org_a).exists())
        self.assertTrue(StudentGroup.objects.filter(name="Super B", organization=self.org_b).exists())


class TeacherExamListOwnershipFilteringTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="teacher_exam_owner",
            email="teacher_exam_owner@example.com",
            password="StrongPass123!",
        )
        self.other_teacher = User.objects.create_user(
            username="teacher_exam_other",
            email="teacher_exam_other@example.com",
            password="StrongPass123!",
        )

        self.org_a = Organization.objects.create(
            name="Exam Org A",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self.org_b = Organization.objects.create(
            name="Exam Org B",
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

        other_profile = self.other_teacher.profile
        other_profile.organization = self.org_a
        other_profile.organization_type = self.org_a.org_type
        other_profile.role = ProfileRole.TEACHER
        other_profile.save()

        self.exam_visible = Exam.objects.create(
            author=self.teacher,
            title="Visible Exam",
            is_active=True,
        )
        self.exam_other_tenant = Exam.objects.create(
            author=self.teacher,
            title="Other Tenant Exam",
            organization_id=999,
            is_active=True,
        )
        self.exam_other_author = Exam.objects.create(
            author=self.other_teacher,
            title="Other Author Exam",
            is_active=True,
        )

        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

    def test_teacher_exam_list_is_owner_and_tenant_scoped(self):
        response = self.client.get(reverse("exams:teacher_exam_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.exam_visible.title)
        self.assertNotContains(response, self.exam_other_tenant.title)
        self.assertNotContains(response, self.exam_other_author.title)


class StudentExamVisibilityFilteringTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="student_exam_teacher",
            email="student_exam_teacher@example.com",
            password="StrongPass123!",
        )
        self.student = User.objects.create_user(
            username="student_exam_student",
            email="student_exam_student@example.com",
            password="StrongPass123!",
        )
        self.viewer_teacher = User.objects.create_user(
            username="viewer_teacher",
            email="viewer_teacher@example.com",
            password="StrongPass123!",
        )
        self.superadmin = User.objects.create_superuser(
            username="viewer_superadmin",
            email="viewer_superadmin@example.com",
            password="StrongPass123!",
        )

        self.org_a = Organization.objects.create(
            name="Student Exam Org A",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )

        teacher_profile = self.teacher.profile
        teacher_profile.organization = self.org_a
        teacher_profile.organization_type = self.org_a.org_type
        teacher_profile.role = ProfileRole.TEACHER
        teacher_profile.save()

        student_profile = self.student.profile
        student_profile.organization = self.org_a
        student_profile.organization_type = self.org_a.org_type
        student_profile.role = ProfileRole.STUDENT
        student_profile.save()

        viewer_teacher_profile = self.viewer_teacher.profile
        viewer_teacher_profile.organization = self.org_a
        viewer_teacher_profile.organization_type = self.org_a.org_type
        viewer_teacher_profile.role = ProfileRole.TEACHER
        viewer_teacher_profile.save()

        self.assigned_exam = Exam.objects.create(
            author=self.teacher,
            title="Assigned Student Exam",
            is_active=True,
            is_public=False,
        )
        self.assigned_exam.allowed_users.add(self.student)

        self.assigned_course = Course.objects.create(
            owner=self.teacher,
            title="Student Course Assignment",
            status="published",
        )
        CourseMembership.objects.create(
            course=self.assigned_course,
            user=self.student,
            role="student",
        )

        self.course_assigned_exam = Exam.objects.create(
            author=self.teacher,
            title="Course Assigned Exam",
            is_active=True,
            is_public=False,
            course=self.assigned_course,
        )

        self.assigned_public_exam = Exam.objects.create(
            author=self.teacher,
            title="Assigned Public Exam",
            is_active=True,
            is_public=True,
        )
        self.assigned_public_exam.allowed_users.add(self.student)

        self.code_assigned_exam = Exam.objects.create(
            author=self.teacher,
            title="Code Assigned Exam",
            is_active=True,
            is_public=False,
            access_code="123456",
        )
        self.code_assigned_exam.allowed_users.add(self.student)

        self.code_unassigned_exam = Exam.objects.create(
            author=self.teacher,
            title="Code Unassigned Exam",
            is_active=True,
            is_public=False,
            access_code="123456",
        )

        self.unassigned_public_exam = Exam.objects.create(
            author=self.teacher,
            title="Unassigned Public Exam",
            is_active=True,
            is_public=True,
        )

        self.unassigned_private_exam = Exam.objects.create(
            author=self.teacher,
            title="Unassigned Private Exam",
            is_active=True,
            is_public=False,
        )

        self.other_tenant_exam = Exam.objects.create(
            author=self.teacher,
            title="Assigned But Other Tenant",
            is_active=True,
            is_public=False,
            organization_id=999,
        )
        self.other_tenant_exam.allowed_users.add(self.student)

        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

    def test_student_available_exam_list_includes_public_exams_in_active_tenant(self):
        response = self.client.get(reverse("exams:student_exam_list"), {"q": self.course_assigned_exam.title})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course_assigned_exam.title)

        response = self.client.get(reverse("exams:student_exam_list"), {"q": self.unassigned_public_exam.title})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.unassigned_public_exam.title)

        response = self.client.get(reverse("exams:student_exam_list"), {"q": self.other_tenant_exam.title})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.other_tenant_exam.slug)

    def test_student_assigned_exam_list_shows_only_assigned_in_active_tenant(self):
        response = self.client.get(reverse("exams:assigned_exam_list"), {"q": self.assigned_exam.title})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.assigned_exam.title)

        response = self.client.get(reverse("exams:assigned_exam_list"), {"q": self.course_assigned_exam.title})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course_assigned_exam.title)

        response = self.client.get(reverse("exams:assigned_exam_list"), {"q": self.code_assigned_exam.title})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.code_assigned_exam.title)

        response = self.client.get(reverse("exams:assigned_exam_list"), {"q": self.assigned_public_exam.title})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.assigned_public_exam.slug)

        response = self.client.get(reverse("exams:assigned_exam_list"), {"q": self.unassigned_public_exam.title})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.unassigned_public_exam.slug)

        response = self.client.get(reverse("exams:assigned_exam_list"), {"q": self.unassigned_private_exam.title})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.unassigned_private_exam.slug)

        response = self.client.get(reverse("exams:assigned_exam_list"), {"q": self.other_tenant_exam.title})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.other_tenant_exam.slug)

    def test_course_assigned_exam_can_be_started_by_student(self):
        response = self.client.get(reverse("exams:start_exam", args=[self.course_assigned_exam.slug]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.course_assigned_exam.attempts.filter(user=self.student).exists())

    def test_unassigned_private_exam_cannot_be_started(self):
        response = self.client.get(reverse("exams:start_exam", args=[self.unassigned_private_exam.slug]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("exams:student_exam_list"))
        self.assertFalse(self.unassigned_private_exam.attempts.filter(user=self.student).exists())

    def test_assigned_exam_with_code_requires_code_before_start(self):
        response = self.client.get(reverse("exams:start_exam", args=[self.code_assigned_exam.slug]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("exams:student_exam_list"))
        self.assertFalse(self.code_assigned_exam.attempts.filter(user=self.student).exists())

    def test_assigned_exam_with_code_starts_after_correct_code(self):
        response = self.client.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": self.code_assigned_exam.slug, "access_code": "123456"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.code_assigned_exam.attempts.filter(user=self.student).exists())

    def test_unassigned_exam_with_code_cannot_start_even_with_valid_code(self):
        response = self.client.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": self.code_unassigned_exam.slug, "access_code": "123456"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("exams:student_exam_list"))
        self.assertFalse(self.code_unassigned_exam.attempts.filter(user=self.student).exists())

    def test_public_exams_are_visible_to_other_authenticated_roles(self):
        self.client.force_login(self.viewer_teacher)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()
        teacher_response = self.client.get(reverse("exams:student_exam_list"))
        self.assertEqual(teacher_response.status_code, 200)
        self.assertContains(teacher_response, self.unassigned_public_exam.title)

        self.client.force_login(self.superadmin)
        superadmin_response = self.client.get(reverse("exams:student_exam_list"))
        self.assertEqual(superadmin_response.status_code, 200)
        self.assertContains(superadmin_response, self.unassigned_public_exam.title)
