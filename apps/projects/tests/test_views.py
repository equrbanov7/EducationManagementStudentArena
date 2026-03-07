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
from apps.organizations.models import Organization
from apps.projects.models import Project, ProjectSubmission
from core.constants import OrganizationType

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


class ProjectReviewSubmissionNavigationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("project_review_teacher", "project_review_teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("project_review_student", "project_review_student@example.com", "StrongPass123!")
        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])
        self.course = Course.objects.create(owner=self.teacher, title="Project Review Course", status="published")
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

    def test_review_submissions_reads_selected_submission_query_param(self):
        self.client.login(username="project_review_teacher", password="StrongPass123!")
        response = self.client.get(
            reverse("projects:review_project_submissions", kwargs={"pk": self.project.id}),
            {"submission": str(self.submission.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_submission_id"], str(self.submission.id))
        self.assertContains(response, "results-filter-card")
        self.assertContains(response, "resultsFilterSearchInput")

    def test_review_submissions_prefers_explicit_return_to_for_back_url(self):
        self.client.login(username="project_review_teacher", password="StrongPass123!")
        return_to = f"{reverse('accounts:profile')}?section=review-results"
        response = self.client.get(
            reverse("projects:review_project_submissions", kwargs={"pk": self.project.id}),
            {"return_to": return_to},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["back_url"], return_to)


class ProjectUploadSecurityTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("project_upload_teacher", "put@example.com", "StrongPass123!")
        self.student = User.objects.create_user("project_upload_student", "pus@example.com", "StrongPass123!")
        self.course = Course.objects.create(owner=self.teacher, title="Project Upload Course", status="published")
        self.project = Project.objects.create(
            course=self.course,
            title="Project Upload Security",
            description="Upload security test",
            start_date=timezone.now() - timedelta(days=1),
            deadline=timezone.now() + timedelta(days=1),
            status="active",
        )
        self.project.assigned_students.add(self.student)
        self.client.force_login(self.student)

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

        self.course_a = Course.objects.create(owner=self.teacher_a, title="Project Course A", status="published")
        self.course_b = Course.objects.create(owner=self.teacher_b, title="Project Course B", status="published")

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
        self.student.profile.role = ProfileRole.STUDENT
        self.student.profile.save(update_fields=["role", "updated_at"])

        self.course = Course.objects.create(owner=self.teacher, title="Project Visibility Course", status="published")
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
        self.client.force_login(self.student)

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
