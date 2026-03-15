"""
View tests for projects app.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.courses.models import Course
from apps.organizations.models import Membership, Organization
from apps.projects.models import Project, ProjectSubmission
from core.constants import OrganizationType

User = get_user_model()


def _assign_user_to_org(user, organization, profile_role, *, membership_role_name=None):
    membership_role_name = membership_role_name or {
        ProfileRole.TEACHER: "teacher",
        ProfileRole.ASSISTANT_TEACHER: "member",
        ProfileRole.STUDENT: "student",
    }.get(profile_role, "member")

    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={
            "role": organization.roles.get(name=membership_role_name),
            "is_primary": True,
            "is_active": True,
        },
    )


def _login_with_org(client, user, organization):
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()


class ProjectDetailBackUrlTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("project_teacher", "project_teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("project_student", "project_student@example.com", "StrongPass123!")
        self.organization = Organization.objects.create(
            name="Project Detail Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)
        self.course = Course.objects.create(owner=self.teacher, title="Project Course", status="published", organization=self.organization)
        self.project = Project.objects.create(
            course=self.course,
            title="Project Back Url",
            description="Project back url test",
            start_date=timezone.now() - timedelta(days=1),
            deadline=timezone.now() + timedelta(days=2),
            status="active",
        )
        self.project.assigned_students.add(self.student)

    def _login_as(self, user):
        _login_with_org(self.client, user, self.organization)

    def test_project_detail_defaults_back_to_course_dashboard(self):
        self._login_as(self.student)
        response = self.client.get(reverse("projects:project_detail", kwargs={"pk": self.project.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["back_url"],
            reverse("courses:course_dashboard", kwargs={"course_id": self.course.id}),
        )

    def test_project_detail_returns_to_assigned_tasks_when_opened_from_profile_tasks(self):
        self._login_as(self.student)
        response = self.client.get(
            reverse("projects:project_detail", kwargs={"pk": self.project.id}),
            {"from_section": "assigned-exams", "assigned_type": "independent"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["back_url"],
            f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type=independent",
        )

    def test_project_detail_includes_submit_confirmation_modal(self):
        self._login_as(self.student)
        response = self.client.get(reverse("projects:project_detail", kwargs={"pk": self.project.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "courseActionConfirmModal")
        self.assertContains(response, "Bu kurs işini göndərmək istədiyinizə əminsiniz?")


class ProjectReviewSubmissionNavigationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("project_review_teacher", "project_review_teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("project_review_student", "project_review_student@example.com", "StrongPass123!")
        self.organization = Organization.objects.create(
            name="Project Review Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)
        self.course = Course.objects.create(owner=self.teacher, title="Project Review Course", status="published", organization=self.organization)
        self.project = Project.objects.create(
            course=self.course,
            title="Project Review",
            description="Project review test",
            start_date=timezone.now() - timedelta(days=1),
            deadline=timezone.now() + timedelta(days=2),
            status="active",
        )
        self.submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            content="Test submission",
            status="pending",
        )

    def _login_teacher(self):
        _login_with_org(self.client, self.teacher, self.organization)

    def test_review_submissions_reads_selected_submission_query_param(self):
        self._login_teacher()
        response = self.client.get(
            reverse("projects:review_project_submissions", kwargs={"pk": self.project.id}),
            {"submission": str(self.submission.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_submission_id"], str(self.submission.id))
        self.assertContains(response, "results-filter-card")
        self.assertContains(response, "resultsFilterSearchInput")

    def test_review_submissions_renders_bulk_delete_controls(self):
        self._login_teacher()
        response = self.client.get(reverse("projects:review_project_submissions", kwargs={"pk": self.project.id}))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_delete_submissions"])
        self.assertContains(response, "selectedProjectCount")
        self.assertContains(response, "deleteSelectedProjectsBtn")
        self.assertContains(response, "js-project-submission-checkbox")

    def test_delete_project_submissions_removes_selected_rows(self):
        another_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            content="Another delete target",
            status="pending",
        )

        self._login_teacher()
        response = self.client.post(
            reverse("projects:delete_project_submissions", kwargs={"pk": self.project.id}),
            {
                "submission_ids": [str(self.submission.id), str(another_submission.id)],
                "next": reverse("projects:review_project_submissions", kwargs={"pk": self.project.id}),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProjectSubmission.objects.filter(id=self.submission.id).exists())
        self.assertFalse(ProjectSubmission.objects.filter(id=another_submission.id).exists())

    def test_review_submissions_prefers_explicit_return_to_for_back_url(self):
        self._login_teacher()
        return_to = f"{reverse('accounts:profile')}?section=review-results"
        response = self.client.get(
            reverse("projects:review_project_submissions", kwargs={"pk": self.project.id}),
            {"return_to": return_to},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["back_url"], return_to)

    def test_review_submissions_hides_student_name_for_first_five_minutes_then_reveals(self):
        self._login_teacher()
        response = self.client.get(reverse("projects:review_project_submissions", kwargs={"pk": self.project.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonim tələbə")
        self.assertContains(response, "Yoxla")
        self.assertNotContains(response, self.student.username)
        self.assertNotContains(response, 'data-review-countdown="')

        self.submission.submitted_at = timezone.now() - timedelta(minutes=6)
        self.submission.save(update_fields=["submitted_at"])

        revealed_response = self.client.get(reverse("projects:review_project_submissions", kwargs={"pk": self.project.id}))
        self.assertEqual(revealed_response.status_code, 200)
        self.assertContains(revealed_response, self.student.username)
        self.assertNotContains(revealed_response, "Anonim tələbə")

    def test_review_submissions_shows_recheck_then_view_after_window_closes(self):
        self.submission.status = "graded"
        self.submission.grade = "77.00"
        self.submission.feedback = "Initial review"
        self.submission.graded_at = timezone.now()
        self.submission.save(update_fields=["status", "grade", "feedback", "graded_at"])

        self._login_teacher()
        response = self.client.get(reverse("projects:review_project_submissions", kwargs={"pk": self.project.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yenidən yoxla")
        self.assertContains(response, "Anonim tələbə")
        self.assertContains(response, 'data-review-countdown="')
        self.assertEqual(response.context["submissions"][0].review_action_label, "Yenidən yoxla")

        self.submission.graded_at = timezone.now() - timedelta(minutes=6)
        self.submission.save(update_fields=["graded_at"])

        locked_response = self.client.get(reverse("projects:review_project_submissions", kwargs={"pk": self.project.id}))
        self.assertEqual(locked_response.status_code, 200)
        self.assertContains(locked_response, "Bax")
        self.assertContains(locked_response, self.student.username)
        self.assertEqual(locked_response.context["submissions"][0].review_action_label, "Bax")

    def test_review_submissions_includes_confirm_modal_and_preserves_grade_value(self):
        self.submission.status = "graded"
        self.submission.grade = "30.00"
        self.submission.feedback = "Saved project score"
        self.submission.graded_at = timezone.now()
        self.submission.save(update_fields=["status", "grade", "feedback", "graded_at"])

        self._login_teacher()
        response = self.client.get(
            reverse("projects:review_project_submissions", kwargs={"pk": self.project.id}),
            {"submission": str(self.submission.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "courseActionConfirmModal")
        self.assertContains(response, 'id="grade-input"')
        self.assertContains(response, 'step="1"')
        self.assertContains(response, 'data-grade="30"')


class ProjectUploadSecurityTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("project_upload_teacher", "put@example.com", "StrongPass123!")
        self.student = User.objects.create_user("project_upload_student", "pus@example.com", "StrongPass123!")
        self.organization = Organization.objects.create(
            name="Project Upload Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)
        self.course = Course.objects.create(owner=self.teacher, title="Project Upload Course", status="published", organization=self.organization)
        self.project = Project.objects.create(
            course=self.course,
            title="Project Upload Security",
            description="Upload security test",
            start_date=timezone.now() - timedelta(days=1),
            deadline=timezone.now() + timedelta(days=1),
            status="active",
        )
        self.project.assigned_students.add(self.student)
        _login_with_org(self.client, self.student, self.organization)

    def test_submit_project_rejects_php_upload(self):
        payload = {
            "content": "malicious upload",
            "file": SimpleUploadedFile("shell.php", b"<?php echo 'pwn';", content_type="application/x-httpd-php"),
        }
        response = self.client.post(reverse("projects:submit_project", kwargs={"pk": self.project.id}), data=payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProjectSubmission.objects.count(), 0)

    def test_submit_project_rejects_exe_upload(self):
        payload = {
            "content": "malicious upload",
            "file": SimpleUploadedFile(
                "virus.exe",
                b"MZ\x00\x00\x00\x00",
                content_type="application/x-msdownload",
            ),
        }
        response = self.client.post(reverse("projects:submit_project", kwargs={"pk": self.project.id}), data=payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProjectSubmission.objects.count(), 0)

    def test_submit_project_randomizes_filename_for_allowed_file(self):
        payload = {
            "content": "safe upload",
            "file": SimpleUploadedFile("report.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n", content_type="application/pdf"),
        }
        response = self.client.post(reverse("projects:submit_project", kwargs={"pk": self.project.id}), data=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProjectSubmission.objects.count(), 1)
        submission = ProjectSubmission.objects.first()
        self.assertTrue(submission.file.name.startswith("projects/submissions/"))
        self.assertTrue(submission.file.name.endswith(".pdf"))
        self.assertFalse(submission.file.name.endswith("/report.pdf"))

    def test_submit_project_rejects_unassigned_student(self):
        other_student = User.objects.create_user(
            "project_upload_unassigned",
            "puu@example.com",
            "StrongPass123!",
        )
        _assign_user_to_org(other_student, self.organization, ProfileRole.STUDENT)
        _login_with_org(self.client, other_student, self.organization)

        response = self.client.post(
            reverse("projects:submit_project", kwargs={"pk": self.project.id}),
            {"content": "should be rejected"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(ProjectSubmission.objects.count(), 0)


class ProjectTenantIsolationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher_a = User.objects.create_user("project_tenant_teacher_a", "pta@example.com", "StrongPass123!")
        self.teacher_b = User.objects.create_user("project_tenant_teacher_b", "ptb@example.com", "StrongPass123!")
        self.student_a = User.objects.create_user("project_tenant_student_a", "psa@example.com", "StrongPass123!")
        self.student_b = User.objects.create_user("project_tenant_student_b", "psb@example.com", "StrongPass123!")

        self.org_a = Organization.objects.create(
            name="Project Org A",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher_a,
            status="active",
            is_active=True,
        )
        self.org_b = Organization.objects.create(
            name="Project Org B",
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

        self.course_a = Course.objects.create(owner=self.teacher_a, title="Project Course A", status="published", organization=self.org_a)
        self.course_b = Course.objects.create(owner=self.teacher_b, title="Project Course B", status="published", organization=self.org_b)

        self.project_b = Project.objects.create(
            course=self.course_b,
            title="Tenant B Project",
            description="Tenant B project",
            start_date=timezone.now() - timedelta(days=1),
            deadline=timezone.now() + timedelta(days=1),
            status="active",
        )
        self.project_b.assigned_students.add(self.student_b)

        self.client.force_login(self.teacher_a)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

    def test_api_get_groups_blocks_cross_tenant_course_id(self):
        response = self.client.get(reverse("projects:api_get_groups"), {"course_id": self.course_b.id})
        self.assertEqual(response.status_code, 404)

    def test_project_detail_blocks_cross_tenant_project_id(self):
        self.client.force_login(self.student_a)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.get(reverse("projects:project_detail", kwargs={"pk": self.project_b.id}))
        self.assertEqual(response.status_code, 404)


class ProjectReviewVisibilityTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("project_visibility_teacher", "pvt@example.com", "StrongPass123!")
        self.student = User.objects.create_user("project_visibility_student", "pvs@example.com", "StrongPass123!")
        self.organization = Organization.objects.create(
            name="Project Visibility Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)

        self.course = Course.objects.create(owner=self.teacher, title="Project Visibility Course", status="published", organization=self.organization)
        self.project = Project.objects.create(
            course=self.course,
            title="Project Visibility",
            description="Visibility test",
            start_date=timezone.now() - timedelta(days=1),
            deadline=timezone.now() + timedelta(days=1),
            status="active",
            max_score=100,
        )
        self.project.assigned_students.add(self.student)
        self.submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.student,
            content="Visibility answer",
            status="graded",
            grade="88.25",
            feedback="Project feedback should wait",
            graded_at=timezone.now(),
        )

    def test_student_views_hide_project_result_until_review_window_closes(self):
        _login_with_org(self.client, self.student, self.organization)

        hidden_detail_response = self.client.get(reverse("projects:project_detail", kwargs={"pk": self.project.id}))
        self.assertEqual(hidden_detail_response.status_code, 200)
        self.assertFalse(hidden_detail_response.context["user_submissions"][0].show_review_data)
        self.assertNotContains(hidden_detail_response, "88.25")
        self.assertContains(hidden_detail_response, 'data-review-countdown="')

        hidden_submissions_response = self.client.get(reverse("projects:my_submissions", kwargs={"pk": self.project.id}))
        self.assertEqual(hidden_submissions_response.status_code, 200)
        self.assertFalse(hidden_submissions_response.context["submissions"][0].show_review_data)
        self.assertNotContains(hidden_submissions_response, "Project feedback should wait")
        self.assertNotContains(hidden_submissions_response, "88.25")
        self.assertContains(hidden_submissions_response, 'data-review-countdown="')

        self.submission.graded_at = timezone.now() - timedelta(minutes=6)
        self.submission.save(update_fields=["graded_at"])

        visible_detail_response = self.client.get(reverse("projects:project_detail", kwargs={"pk": self.project.id}))
        self.assertEqual(visible_detail_response.status_code, 200)
        self.assertTrue(visible_detail_response.context["user_submissions"][0].show_review_data)
        self.assertContains(visible_detail_response, "88,25")

        visible_submissions_response = self.client.get(reverse("projects:my_submissions", kwargs={"pk": self.project.id}))
        self.assertEqual(visible_submissions_response.status_code, 200)
        self.assertTrue(visible_submissions_response.context["submissions"][0].show_review_data)
        self.assertContains(visible_submissions_response, "Project feedback should wait")
        self.assertContains(visible_submissions_response, "88,25")


class RosterAPIAuthorizationTest(TestCase):
    """Test authorization for roster API endpoints (api_get_groups and api_get_students)"""

    def setUp(self):
        self.client = Client()

        # Create users
        self.owner = User.objects.create_user("owner", "owner@example.com", "StrongPass123!")
        self.teacher = User.objects.create_user("teacher", "teacher@example.com", "StrongPass123!")
        self.assistant = User.objects.create_user("assistant", "assistant@example.com", "StrongPass123!")
        self.student = User.objects.create_user("student", "student@example.com", "StrongPass123!")
        self.unauthorized_user = User.objects.create_user("unauthorized", "unauthorized@example.com", "StrongPass123!")

        self.organization = Organization.objects.create(
            name="Project Roster Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.owner, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(
            self.assistant,
            self.organization,
            ProfileRole.ASSISTANT_TEACHER,
            membership_role_name="member",
        )
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)
        _assign_user_to_org(self.unauthorized_user, self.organization, ProfileRole.STUDENT)

        # Create course
        self.course = Course.objects.create(owner=self.owner, title="Test Course", status="published", organization=self.organization)

        # Add memberships
        from apps.courses.models import CourseMembership

        CourseMembership.objects.create(course=self.course, user=self.teacher, role="teacher")
        CourseMembership.objects.create(course=self.course, user=self.assistant, role="assistant")
        CourseMembership.objects.create(course=self.course, user=self.student, role="student", group_name="Group A")

    def _login_as(self, user):
        _login_with_org(self.client, user, self.organization)

    def test_api_get_groups_owner_can_access(self):
        """Course owner should be able to access groups"""
        self._login_as(self.owner)
        response = self.client.get(reverse("projects:api_get_groups"), {"course_id": self.course.id})
        self.assertEqual(response.status_code, 200)
        self.assertIn("groups", response.json())

    def test_api_get_groups_teacher_can_access(self):
        """Teacher with teacher role should be able to access groups"""
        self._login_as(self.teacher)
        response = self.client.get(reverse("projects:api_get_groups"), {"course_id": self.course.id})
        self.assertEqual(response.status_code, 200)
        self.assertIn("groups", response.json())

    def test_api_get_groups_assistant_can_access(self):
        """User with assistant role should be able to access groups"""
        self._login_as(self.assistant)
        response = self.client.get(reverse("projects:api_get_groups"), {"course_id": self.course.id})
        self.assertEqual(response.status_code, 200)
        self.assertIn("groups", response.json())

    def test_api_get_groups_student_denied(self):
        """Student should be denied access to groups"""
        self._login_as(self.student)
        response = self.client.get(reverse("projects:api_get_groups"), {"course_id": self.course.id})
        self.assertEqual(response.status_code, 403)

    def test_api_get_groups_unauthorized_user_denied(self):
        """Unauthorized user should be denied access to groups"""
        self._login_as(self.unauthorized_user)
        response = self.client.get(reverse("projects:api_get_groups"), {"course_id": self.course.id})
        self.assertEqual(response.status_code, 403)

    def test_api_get_students_owner_can_access(self):
        """Course owner should be able to access students"""
        self._login_as(self.owner)
        response = self.client.get(reverse("projects:api_get_students"), {"course_id": self.course.id, "groups": "Group A"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("students", response.json())

    def test_api_get_students_teacher_can_access(self):
        """Teacher with teacher role should be able to access students"""
        self._login_as(self.teacher)
        response = self.client.get(reverse("projects:api_get_students"), {"course_id": self.course.id, "groups": "Group A"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("students", response.json())

    def test_api_get_students_assistant_can_access(self):
        """User with assistant role should be able to access students"""
        self._login_as(self.assistant)
        response = self.client.get(reverse("projects:api_get_students"), {"course_id": self.course.id, "groups": "Group A"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("students", response.json())

    def test_api_get_students_student_denied(self):
        """Student should be denied access to students list"""
        self._login_as(self.student)
        response = self.client.get(reverse("projects:api_get_students"), {"course_id": self.course.id, "groups": "Group A"})
        self.assertEqual(response.status_code, 403)

    def test_api_get_students_unauthorized_user_denied(self):
        """Unauthorized user should be denied access to students list"""
        self._login_as(self.unauthorized_user)
        response = self.client.get(reverse("projects:api_get_students"), {"course_id": self.course.id, "groups": "Group A"})
        self.assertEqual(response.status_code, 403)
