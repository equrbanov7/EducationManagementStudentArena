"""
View tests for assignments app.
"""

import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.assignments.models import Assignment, Submission
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


class AssignmentSubmissionRegressionTest(TestCase):
    def setUp(self):
        self.temp_media = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.temp_media)
        self.media_override.enable()

        self.client = Client()
        self.teacher = User.objects.create_user("assignment_reg_teacher", "areg_t@example.com", "StrongPass123!")
        self.student = User.objects.create_user("assignment_reg_student", "areg_s@example.com", "StrongPass123!")

        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])
        self.student.profile.role = ProfileRole.STUDENT
        self.student.profile.save(update_fields=["role", "updated_at"])

        self.course = Course.objects.create(owner=self.teacher, title="Assignment Regression Course", status="published")
        self.assignment = Assignment.objects.create(
            course=self.course,
            title="Assignment Regression",
            start_date=timezone.now() - timedelta(days=1),
            due_date=timezone.now() + timedelta(days=2),
            status="published",
            max_attempts=3,
        )
        self.assignment.assigned_students.add(self.student)

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.temp_media, ignore_errors=True)
        super().tearDown()

    def test_assignment_views_render_existing_submission_using_user_relation(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="Existing answer",
            status="submitted",
        )

        self.client.force_login(self.student)

        detail_response = self.client.get(reverse("assignments:assignment_detail", kwargs={"pk": self.assignment.id}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(list(detail_response.context["user_submissions"]), [submission])

        my_submissions_response = self.client.get(reverse("assignments:my_submissions", kwargs={"pk": self.assignment.id}))
        self.assertEqual(my_submissions_response.status_code, 200)
        self.assertEqual(list(my_submissions_response.context["submissions"]), [submission])

    def test_submit_assignment_stores_uploaded_file_in_json_payload(self):
        self.client.force_login(self.student)

        response = self.client.post(
            reverse("assignments:submit_assignment", kwargs={"pk": self.assignment.id}),
            data={
                "content": "New answer",
                "file": SimpleUploadedFile(
                    "answer.pdf",
                    b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n",
                    content_type="application/pdf",
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        submission = Submission.objects.get()
        self.assertEqual(submission.user, self.student)
        self.assertEqual(submission.attempt_number, 1)
        self.assertEqual(submission.files[0]["name"], "answer.pdf")
        self.assertTrue(submission.files[0]["path"].startswith("assignments/submissions/"))
        self.assertTrue(submission.files[0]["path"].endswith(".pdf"))
        self.assertFalse(submission.files[0]["path"].endswith("/answer.pdf"))
        self.assertEqual(submission.file.name, "answer.pdf")

    def test_review_submissions_uses_user_relation_for_select_related(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="Review me",
            status="submitted",
        )

        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse("assignments:review_assignment_submissions", kwargs={"pk": self.assignment.id}),
            {"submission": str(submission.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_submission_id"], str(submission.id))
        self.assertContains(response, "answers-stat-grid")
        self.assertContains(response, "answers-table-card__header")

    def test_student_submit_then_teacher_grade_flow_hides_results_until_review_window_closes(self):
        self.client.force_login(self.student)

        detail_response = self.client.get(reverse("assignments:assignment_detail", kwargs={"pk": self.assignment.id}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, self.assignment.title)

        submit_response = self.client.post(
            reverse("assignments:submit_assignment", kwargs={"pk": self.assignment.id}),
            data={
                "content": "Flow answer",
                "file": SimpleUploadedFile(
                    "flow.pdf",
                    b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n",
                    content_type="application/pdf",
                ),
            },
        )
        self.assertEqual(submit_response.status_code, 200)
        self.assertTrue(submit_response.json()["success"])

        submission = Submission.objects.get()

        my_submissions_response = self.client.get(reverse("assignments:my_submissions", kwargs={"pk": self.assignment.id}))
        self.assertEqual(my_submissions_response.status_code, 200)
        self.assertContains(my_submissions_response, "flow.pdf")

        self.client.force_login(self.teacher)
        review_response = self.client.get(
            reverse("assignments:review_assignment_submissions", kwargs={"pk": self.assignment.id}),
            {"submission": str(submission.id)},
        )
        self.assertEqual(review_response.status_code, 200)
        self.assertContains(review_response, "Flow answer")

        grade_response = self.client.post(
            reverse("assignments:grade_submission", kwargs={"pk": submission.id}),
            data={"grade": "95", "feedback": "Looks good"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(grade_response.status_code, 200)
        self.assertTrue(grade_response.json()["success"])

        submission.refresh_from_db()
        self.assertEqual(submission.status, "graded")
        self.assertEqual(float(submission.grade), 95.0)
        self.assertEqual(submission.feedback, "Looks good")

        self.client.force_login(self.student)
        hidden_detail_response = self.client.get(reverse("assignments:assignment_detail", kwargs={"pk": self.assignment.id}))
        self.assertEqual(hidden_detail_response.status_code, 200)
        self.assertFalse(hidden_detail_response.context["user_submissions"][0].show_review_data)
        self.assertContains(hidden_detail_response, 'data-review-countdown="')
        self.assertNotContains(hidden_detail_response, "5 dəq. sonra")

        hidden_submissions_response = self.client.get(reverse("assignments:my_submissions", kwargs={"pk": self.assignment.id}))
        self.assertEqual(hidden_submissions_response.status_code, 200)
        self.assertFalse(hidden_submissions_response.context["submissions"][0].show_review_data)
        self.assertNotContains(hidden_submissions_response, "Looks good")
        self.assertContains(hidden_submissions_response, 'data-review-countdown="')
        self.assertNotContains(hidden_submissions_response, "5 dəq. sonra")

        submission.graded_at = timezone.now() - timedelta(minutes=6)
        submission.save(update_fields=["graded_at"])

        visible_detail_response = self.client.get(reverse("assignments:assignment_detail", kwargs={"pk": self.assignment.id}))
        self.assertEqual(visible_detail_response.status_code, 200)
        self.assertTrue(visible_detail_response.context["user_submissions"][0].show_review_data)
        self.assertContains(visible_detail_response, "95")

        visible_submissions_response = self.client.get(reverse("assignments:my_submissions", kwargs={"pk": self.assignment.id}))
        self.assertEqual(visible_submissions_response.status_code, 200)
        self.assertTrue(visible_submissions_response.context["submissions"][0].show_review_data)
        self.assertContains(visible_submissions_response, "Looks good")
        self.assertContains(visible_submissions_response, "95")
