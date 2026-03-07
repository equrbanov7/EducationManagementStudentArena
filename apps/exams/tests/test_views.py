"""
View tests for exams app.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion, ExamQuestionOption, StudentGroup
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
        self.superadmin = User.objects.create_superuser(
            "superadmin_groups", "superadmin_groups@example.com", "StrongPass123!"
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
            self._group_payload(
                name="A Group", primary_teacher=str(self.teacher.id), assigned_teachers=[str(self.teacher.id)]
            ),
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
        self.assertEqual(
            self.client.post(reverse("exams:teacher_create_group"), self._group_payload(name="Blocked")).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("exams:teacher_update_group", args=[group.id]), self._group_payload(name="Blocked Update")
            ).status_code,
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
        self.student = User.objects.create_user(
            username="teacher_exam_student",
            email="teacher_exam_student@example.com",
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

        student_profile = self.student.profile
        student_profile.organization = self.org_a
        student_profile.organization_type = self.org_a.org_type
        student_profile.role = ProfileRole.STUDENT
        student_profile.save()

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
        self.course = Course.objects.create(
            owner=self.teacher,
            title="Teacher Exam Course",
            status="published",
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

    def test_modal_create_exam_includes_course_hidden_field_when_requested_from_course_dashboard(self):
        response = self.client.get(
            reverse("exams:create_exam"),
            {"modal": "1", "course": str(self.course.id)},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="course_id"')
        self.assertContains(response, f'value="{self.course.id}"')

    def test_modal_create_exam_links_new_exam_to_requested_course(self):
        response = self.client.post(
            reverse("exams:create_exam") + f"?modal=1&course={self.course.id}",
            {
                "modal": "1",
                "course_id": str(self.course.id),
                "title": "Linked From Course Dashboard",
                "description": "Created via dashboard modal",
                "exam_type": "test",
                "is_active": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)

        created_exam = Exam.objects.get(title="Linked From Course Dashboard")
        self.assertEqual(created_exam.author, self.teacher)
        self.assertEqual(created_exam.course, self.course)

    def test_other_teacher_cannot_edit_or_delete_my_exam(self):
        self.client.force_login(self.other_teacher)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        edit_response = self.client.get(reverse("exams:edit_exam", args=[self.exam_visible.slug]))
        delete_response = self.client.post(reverse("exams:delete_exam", args=[self.exam_visible.slug]))

        self.assertEqual(edit_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)
        self.assertTrue(Exam.objects.filter(id=self.exam_visible.id).exists())

    def test_student_cannot_delete_exam(self):
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.post(reverse("exams:delete_exam", args=[self.exam_visible.slug]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Exam.objects.filter(id=self.exam_visible.id).exists())

    def test_edit_other_tenant_exam_is_not_found(self):
        response = self.client.get(reverse("exams:edit_exam", args=[self.exam_other_tenant.slug]))
        self.assertEqual(response.status_code, 404)

    def test_teacher_exam_detail_defaults_to_generic_back_with_profile_fallback(self):
        response = self.client.get(reverse("exams:teacher_exam_detail", args=[self.exam_visible.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["profile_return_url"], f"{reverse('accounts:profile')}?section=my-exams")
        self.assertContains(response, "Geri")
        self.assertNotContains(response, "Profilə Qayıt")

    def test_teacher_exam_detail_uses_explicit_course_dashboard_return_url(self):
        return_to = reverse("courses:course_dashboard", args=[self.course.id])
        response = self.client.get(
            reverse("exams:teacher_exam_detail", args=[self.exam_visible.slug]),
            {"return_to": return_to},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["profile_return_url"], return_to)
        self.assertContains(response, "Geri")
        self.assertNotContains(response, "Profilə Qayıt")

    def test_teacher_exam_detail_falls_back_to_safe_referer_when_return_to_missing(self):
        referer = reverse("exams:teacher_exam_list")
        response = self.client.get(
            reverse("exams:teacher_exam_detail", args=[self.exam_visible.slug]),
            HTTP_REFERER=referer,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["profile_return_url"], referer)
        self.assertContains(response, "Geri")
        self.assertNotContains(response, "Profilə Qayıt")

    def test_teacher_exam_results_keeps_generic_source_back_label(self):
        return_to = reverse("courses:course_dashboard", args=[self.course.id])
        response = self.client.get(
            reverse("exams:teacher_exam_results", args=[self.exam_visible.slug]),
            {"return_to": return_to},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["profile_return_url"], return_to)
        self.assertContains(response, "Geri")
        self.assertNotContains(response, "Profilə Qayıt")
        self.assertNotContains(response, "Profile geri dön")
        self.assertContains(response, "results-filter-card")
        self.assertContains(response, "resultsFilterSearchInput")

    def test_teacher_exam_results_reveals_student_name_for_test_attempts(self):
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam_visible,
            status="submitted",
        )

        response = self.client.get(reverse("exams:teacher_exam_results", args=[self.exam_visible.slug]))

        self.assertEqual(response.status_code, 200)
        attempts_data = response.context["attempts_data"]
        matching_item = next(item for item in attempts_data if item["attempt"].id == attempt.id)
        self.assertTrue(matching_item["can_view_name"])
        self.assertEqual(matching_item["real_name"], self.student.username)
        self.assertContains(response, self.student.username)

    def test_teacher_exam_results_reveals_student_name_when_written_grade_is_visible_without_timestamp(self):
        written_exam = Exam.objects.create(
            author=self.teacher,
            title="Written Visibility Exam",
            exam_type="written",
            is_active=True,
        )
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=written_exam,
            status="submitted",
            checked_by_teacher=True,
            teacher_score=74,
            teacher_checked_at=None,
        )

        response = self.client.get(reverse("exams:teacher_exam_results", args=[written_exam.slug]))

        self.assertEqual(response.status_code, 200)
        attempts_data = response.context["attempts_data"]
        matching_item = next(item for item in attempts_data if item["attempt"].id == attempt.id)
        self.assertTrue(matching_item["can_view_name"])
        self.assertIsNone(matching_item["seconds_remaining"])
        self.assertEqual(matching_item["real_name"], self.student.username)

    def test_teacher_view_attempt_keeps_generic_source_back_label(self):
        attempt = ExamAttempt.objects.create(
            user=self.teacher,
            exam=self.exam_visible,
            status="submitted",
        )
        return_to = reverse("courses:course_dashboard", args=[self.course.id])
        response = self.client.get(
            reverse("exams:teacher_view_attempt", args=[self.exam_visible.slug, attempt.id]),
            {"return_to": return_to},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["profile_return_url"], return_to)
        self.assertContains(response, "Geri")
        self.assertNotContains(response, "Profilə Qayıt")
        self.assertNotContains(response, "Profile geri dön")


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
        ExamQuestion.objects.create(
            exam=self.course_assigned_exam,
            text="Course question",
            order=1,
            points=1,
        )

        self.course_code_exam = Exam.objects.create(
            author=self.teacher,
            title="Course Code Exam",
            is_active=True,
            is_public=False,
            access_code="777777",
            course=self.assigned_course,
        )
        ExamQuestion.objects.create(
            exam=self.course_code_exam,
            text="Course code question",
            order=1,
            points=1,
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
        ExamQuestion.objects.create(
            exam=self.code_assigned_exam,
            text="Code-protected question",
            order=1,
            points=1,
        )

        self.code_assigned_no_questions_exam = Exam.objects.create(
            author=self.teacher,
            title="Code Assigned No Questions Exam",
            is_active=True,
            is_public=False,
            access_code="654321",
        )
        self.code_assigned_no_questions_exam.allowed_users.add(self.student)

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

    def test_course_dashboard_student_exam_actions_use_info_modal(self):
        response = self.client.get(reverse("courses:course_dashboard", args=[self.assigned_course.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="courseExamInfoBackdrop"')
        self.assertContains(response, "js-open-course-exam-modal")
        self.assertContains(response, f'data-exam-slug="{self.course_assigned_exam.slug}"')
        self.assertContains(response, f'data-exam-slug="{self.course_code_exam.slug}"')
        self.assertContains(response, 'data-requires-code="1"')
        self.assertContains(
            response,
            f'name="next" value="{reverse("courses:course_dashboard", args=[self.assigned_course.id])}"',
        )

    def test_course_dashboard_student_history_button_shows_attempt_count(self):
        ExamAttempt.objects.create(
            user=self.student,
            exam=self.course_assigned_exam,
            status="submitted",
            attempt_number=1,
        )

        response = self.client.get(reverse("courses:course_dashboard", args=[self.assigned_course.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cavablarım (1)")
        self.assertContains(
            response,
            f'{reverse("exams:student_exam_history")}?exam={self.course_assigned_exam.slug}',
        )

    def test_unassigned_private_exam_cannot_be_started(self):
        response = self.client.get(reverse("exams:start_exam", args=[self.unassigned_private_exam.slug]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("exams:student_exam_list"))
        self.assertFalse(self.unassigned_private_exam.attempts.filter(user=self.student).exists())

    def test_unassigned_private_exam_redirects_back_to_profile_assigned_section_when_requested(self):
        response = self.client.get(
            reverse("exams:start_exam", args=[self.unassigned_private_exam.slug]),
            {"from_section": "assigned-exams", "assigned_type": "exams"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type=exams")
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

    def test_assigned_exam_without_questions_cannot_be_started(self):
        response = self.client.get(
            reverse("exams:start_exam", args=[self.assigned_exam.slug]),
            {"from_section": "assigned-exams", "assigned_type": "exams"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type=exams")
        self.assertFalse(self.assigned_exam.attempts.filter(user=self.student).exists())

    def test_assigned_code_exam_without_questions_cannot_be_started(self):
        response = self.client.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": self.code_assigned_no_questions_exam.slug, "access_code": "654321"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("exams:student_exam_list"))
        self.assertFalse(self.code_assigned_no_questions_exam.attempts.filter(user=self.student).exists())

    def test_take_exam_redirects_when_attempt_has_no_questions(self):
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.assigned_exam,
            status="in_progress",
        )

        response = self.client.get(reverse("exams:take_exam", args=[self.assigned_exam.slug, attempt.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("exams:student_exam_list"))

    def test_exam_code_check_rejects_post_without_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.student)
        session = csrf_client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = csrf_client.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": self.code_assigned_exam.slug, "access_code": "123456"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.code_assigned_exam.attempts.filter(user=self.student).exists())

    def test_exam_code_check_sql_injection_payload_does_not_bypass_lookup(self):
        response = self.client.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": "anything' OR 1=1 --", "access_code": "123456"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.code_assigned_exam.attempts.filter(user=self.student).exists())

    def test_unassigned_exam_with_code_cannot_start_even_with_valid_code(self):
        response = self.client.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": self.code_unassigned_exam.slug, "access_code": "123456"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("exams:student_exam_list"))
        self.assertFalse(self.code_unassigned_exam.attempts.filter(user=self.student).exists())

    def test_unassigned_exam_with_code_redirects_back_to_profile_assigned_section_when_requested(self):
        response = self.client.post(
            reverse("exams:exam_code_check"),
            {
                "exam_slug": self.code_unassigned_exam.slug,
                "access_code": "123456",
                "from_section": "assigned-exams",
                "assigned_type": "exams",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type=exams")
        self.assertFalse(self.code_unassigned_exam.attempts.filter(user=self.student).exists())

    def test_other_tenant_exam_cannot_be_started(self):
        response = self.client.get(reverse("exams:start_exam", args=[self.other_tenant_exam.slug]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.other_tenant_exam.attempts.filter(user=self.student).exists())

    def test_other_tenant_exam_code_check_is_not_found(self):
        code_exam = Exam.objects.create(
            author=self.teacher,
            title="Other Tenant Code Exam",
            is_active=True,
            is_public=False,
            access_code="654321",
            organization_id=999,
        )
        code_exam.allowed_users.add(self.student)

        response = self.client.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": code_exam.slug, "access_code": "654321"},
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(code_exam.attempts.filter(user=self.student).exists())

    def test_other_tenant_exam_result_is_not_found(self):
        other_tenant_attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.other_tenant_exam,
            status="submitted",
        )

        response = self.client.get(
            reverse("exams:exam_result", args=[self.other_tenant_exam.slug, other_tenant_attempt.id])
        )
        self.assertEqual(response.status_code, 404)

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

    def test_az_student_exam_list_uses_localized_strings(self):
        with override("az"):
            response = self.client.get(
                reverse("exams:student_exam_list"),
                {"q": self.code_assigned_exam.title},
                HTTP_ACCEPT_LANGUAGE="az",
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "İmtahanlar")
        self.assertContains(response, "Giriş kodu tələb olunur")
        self.assertContains(response, "İmtahana başla")
        self.assertNotContains(response, "Start exam")
        self.assertNotContains(response, "Bu resurs haqqında qısa məlumat")

    def test_az_exam_result_uses_localized_strings(self):
        exam = Exam.objects.create(
            author=self.teacher,
            title="Localized Result Exam",
            is_active=True,
            is_public=False,
        )
        exam.allowed_users.add(self.student)
        question = ExamQuestion.objects.create(
            exam=exam,
            text="Localized question",
            order=1,
            points=1,
        )
        correct_option = ExamQuestionOption.objects.create(
            question=question,
            text="Doğru variant",
            is_correct=True,
        )
        ExamQuestionOption.objects.create(
            question=question,
            text="Yanlış variant",
            is_correct=False,
        )
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=exam,
            status="submitted",
        )
        answer = ExamAnswer.objects.create(
            attempt=attempt,
            question=question,
            is_correct=True,
        )
        answer.selected_options.add(correct_option)
        attempt.recalculate_score()

        with override("az"):
            response = self.client.get(
                reverse("exams:exam_result", args=[exam.slug, attempt.id]),
                HTTP_ACCEPT_LANGUAGE="az",
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nəticəniz")
        self.assertContains(response, "İmtahan statusu")
        self.assertContains(response, "Təhvil verilib")
        self.assertContains(response, "Düzgün")
        self.assertContains(response, "Səhv")
        self.assertNotContains(response, "Subheading posts")
        self.assertNotContains(response, "Submitted")

    def test_filtered_exam_history_shows_only_selected_exam_attempts(self):
        selected_attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.course_assigned_exam,
            status="submitted",
            attempt_number=1,
        )
        other_attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.assigned_exam,
            status="submitted",
            attempt_number=1,
        )
        return_to = reverse("courses:course_dashboard", args=[self.assigned_course.id])

        response = self.client.get(
            reverse("exams:student_exam_history"),
            {"exam": self.course_assigned_exam.slug, "return_to": return_to},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["exam"], self.course_assigned_exam)
        self.assertEqual(response.context["back_url"], return_to)
        attempts = response.context["attempts"]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].id, selected_attempt.id)
        self.assertNotContains(response, other_attempt.exam.title)
        self.assertContains(response, "Mənim cavablarım")
        self.assertContains(response, "Göndərdiyim cavablar")
        self.assertContains(response, "İstifadə olunmuş cəhd")
        self.assertContains(response, "Bax")
        self.assertNotContains(response, "İmtahana başla")

    def test_take_exam_shows_previous_attempts_summary_and_history_link(self):
        previous_attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.course_assigned_exam,
            status="submitted",
            attempt_number=1,
        )

        start_response = self.client.get(
            reverse("exams:start_exam", args=[self.course_assigned_exam.slug]),
            {"next": reverse("courses:course_dashboard", args=[self.assigned_course.id])},
        )

        self.assertEqual(start_response.status_code, 302)
        take_response = self.client.get(start_response.url)

        self.assertEqual(take_response.status_code, 200)
        self.assertContains(take_response, "Əvvəlki cəhdlər")
        self.assertContains(take_response, "Cavablarım (1)")
        self.assertContains(
            take_response,
            reverse("exams:exam_result", args=[self.course_assigned_exam.slug, previous_attempt.id]),
        )


class TeacherViewAttemptSearchPaginationTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="view_attempt_teacher",
            email="view_attempt_teacher@example.com",
            password="StrongPass123!",
        )
        self.student = User.objects.create_user(
            username="view_attempt_student",
            email="view_attempt_student@example.com",
            password="StrongPass123!",
        )

        profile = self.teacher.profile
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["role", "updated_at"])

        self.exam = Exam.objects.create(
            author=self.teacher,
            title="View Attempt Search Exam",
            exam_type="test",
            is_active=True,
        )
        self.attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status="submitted",
        )

        for index in range(1, 8):
            question = ExamQuestion.objects.create(
                exam=self.exam,
                text=f"Sual mətn test {index}",
                order=index,
                points=1,
            )
            correct_option = ExamQuestionOption.objects.create(
                question=question,
                text=f"Doğru cavab {index}",
                is_correct=True,
            )
            ExamQuestionOption.objects.create(
                question=question,
                text=f"Səhv cavab {index}",
                is_correct=False,
            )
            answer = ExamAnswer.objects.create(
                attempt=self.attempt,
                question=question,
                is_correct=True,
            )
            answer.selected_options.add(correct_option)

        self.client.force_login(self.teacher)

    def test_teacher_view_attempt_supports_search_and_questions_pagination(self):
        response = self.client.get(
            reverse("exams:teacher_view_attempt", args=[self.exam.slug, self.attempt.id]),
            {
                "q": "test 7",
                "questions_page": 1,
                "from_section": "review-results",
                "return_to": "/accounts/profile/?section=review-results",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["qa_search_query"], "test 7")
        self.assertEqual(len(response.context["qa_list"]), 1)
        self.assertIn("q=test+7", response.context["qa_pagination_query"])
        self.assertIn("from_section=review-results", response.context["qa_pagination_query"])
        self.assertIn("section%3Dreview-results", response.context["qa_pagination_query"])
        self.assertIn("from_section=review-results", response.context["qa_clear_search_url"])
        self.assertIn("section=review-results", response.context["qa_clear_search_url"])
        self.assertContains(response, 'class="attempt-search-group input-group"')

        response_page_two = self.client.get(
            reverse("exams:teacher_view_attempt", args=[self.exam.slug, self.attempt.id]),
            {"questions_page": 2},
        )
        self.assertEqual(response_page_two.status_code, 200)
        self.assertEqual(response_page_two.context["qa_page"].number, 2)
        self.assertEqual(len(response_page_two.context["qa_list"]), 1)

    def test_teacher_view_attempt_search_matches_option_text(self):
        response = self.client.get(
            reverse("exams:teacher_view_attempt", args=[self.exam.slug, self.attempt.id]),
            {"q": "Doğru cavab 5"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["qa_list"]), 1)
        self.assertContains(response, "Sual mətn test 5")


class StudentExamResultVisibilityWindowTest(TestCase):
    def setUp(self):
        from django.utils import timezone

        self.teacher = User.objects.create_user(
            username="result_visibility_teacher",
            email="result_visibility_teacher@example.com",
            password="StrongPass123!",
        )
        self.student = User.objects.create_user(
            username="result_visibility_student",
            email="result_visibility_student@example.com",
            password="StrongPass123!",
        )

        teacher_profile = self.teacher.profile
        teacher_profile.role = ProfileRole.TEACHER
        teacher_profile.save(update_fields=["role", "updated_at"])

        student_profile = self.student.profile
        student_profile.role = ProfileRole.STUDENT
        student_profile.save(update_fields=["role", "updated_at"])

        self.exam = Exam.objects.create(
            author=self.teacher,
            title="Visibility Written Exam",
            exam_type="written",
            is_active=True,
        )
        self.attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=self.exam,
            status="submitted",
            checked_by_teacher=True,
            teacher_score=82,
            teacher_checked_at=timezone.now(),
        )

        self.client.force_login(self.student)

    def test_exam_result_hidden_while_teacher_review_window_open(self):
        response = self.client.get(reverse("exams:exam_result", args=[self.exam.slug, self.attempt.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("section=my-results", response.url)

    def test_exam_result_visible_after_teacher_review_window_closes(self):
        self.attempt.teacher_checked_at = timezone.now() - timedelta(minutes=6)
        self.attempt.save(update_fields=["teacher_checked_at"])

        response = self.client.get(reverse("exams:exam_result", args=[self.exam.slug, self.attempt.id]))
        self.assertEqual(response.status_code, 200)


class TeacherQuestionsBankViewTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="questions_bank_teacher",
            email="questions_bank_teacher@example.com",
            password="StrongPass123!",
        )

        profile = self.teacher.profile
        profile.role = ProfileRole.TEACHER
        profile.save(update_fields=["role", "updated_at"])

        self.exam = Exam.objects.create(
            author=self.teacher,
            title="Questions Bank Exam",
            exam_type="test",
            is_active=True,
        )

        self.questions = []
        for index in range(1, 15):
            q = ExamQuestion.objects.create(
                exam=self.exam,
                text=f"Alpha Question {index}",
                order=index,
                points=1,
                is_active=True,
            )
            self.questions.append(q)

        self.questions[2].is_active = False
        self.questions[2].save(update_fields=["is_active"])

        self.client.force_login(self.teacher)

    def test_questions_bank_supports_search_status_filter_and_pagination(self):
        response = self.client.get(
            reverse("exams:teacher_questions_bank", args=[self.exam.slug]),
            {"q": "Alpha", "status": "active", "page": 1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "exams/teacher/teacher_questions_bank.html")
        self.assertEqual(response.context["status_filter"], "active")
        self.assertEqual(response.context["search_query"], "Alpha")
        self.assertEqual(response.context["page_obj"].paginator.num_pages, 2)
        self.assertContains(response, "questionSearchInput")

    def test_questions_bank_bulk_deactivate_selected(self):
        selected = [str(self.questions[0].id), str(self.questions[1].id)]
        response = self.client.post(
            reverse("exams:teacher_questions_bank", args=[self.exam.slug]),
            {
                "bulk_action": "deactivate",
                "selected_question_ids": selected,
                "status": "all",
                "q": "",
                "page": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ExamQuestion.objects.get(id=self.questions[0].id).is_active)
        self.assertFalse(ExamQuestion.objects.get(id=self.questions[1].id).is_active)

    def test_questions_bank_bulk_delete_selected(self):
        to_delete = [str(self.questions[3].id), str(self.questions[4].id)]
        response = self.client.post(
            reverse("exams:teacher_questions_bank", args=[self.exam.slug]),
            {
                "bulk_action": "delete",
                "selected_question_ids": to_delete,
                "status": "all",
                "q": "",
                "page": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ExamQuestion.objects.filter(id=self.questions[3].id).exists())
        self.assertFalse(ExamQuestion.objects.filter(id=self.questions[4].id).exists())

    def test_questions_bank_search_matches_option_text_without_duplicates(self):
        ExamQuestionOption.objects.create(
            question=self.questions[0],
            label="A",
            text="Variant debounce açar sözü",
            is_correct=True,
        )
        ExamQuestionOption.objects.create(
            question=self.questions[0],
            label="B",
            text="Variant debounce açar sözü ikinci",
            is_correct=False,
        )

        response = self.client.get(
            reverse("exams:teacher_questions_bank", args=[self.exam.slug]),
            {"q": "debounce açar", "sort": "az"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sort_filter"], "az")
        object_ids = [q.id for q in response.context["page_obj"].object_list]
        self.assertEqual(object_ids, [self.questions[0].id])

    def test_questions_bank_bulk_redirect_preserves_sort_filter(self):
        selected = [str(self.questions[0].id)]
        response = self.client.post(
            reverse("exams:teacher_questions_bank", args=[self.exam.slug]),
            {
                "bulk_action": "deactivate",
                "selected_question_ids": selected,
                "status": "active",
                "q": "Alpha",
                "sort": "za",
                "page": "2",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("q=Alpha", response.url)
        self.assertIn("status=active", response.url)
        self.assertIn("sort=za", response.url)
        self.assertIn("page=2", response.url)
