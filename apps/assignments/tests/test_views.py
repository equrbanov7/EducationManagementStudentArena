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
from apps.courses.models import Course, CourseMembership
from apps.organizations.models import Membership, Organization
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


class AssignmentDetailBackUrlTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("assignment_teacher", "teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("assignment_student", "student@example.com", "StrongPass123!")
        self.organization = Organization.objects.create(
            name="Assignment Detail Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)

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
        _login_with_org(self.client, self.student, self.organization)
        response = self.client.get(reverse("assignments:assignment_detail", kwargs={"pk": self.assignment.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["back_url"],
            reverse("courses:course_dashboard", kwargs={"course_id": self.course.id}),
        )

    def test_assignment_detail_returns_to_assigned_tasks_when_source_is_profile_tasks(self):
        _login_with_org(self.client, self.student, self.organization)
        response = self.client.get(
            reverse("assignments:assignment_detail", kwargs={"pk": self.assignment.id}),
            {"from_section": "assigned-exams", "assigned_type": "assignments"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["back_url"],
            f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type=assignments",
        )

    def test_assignment_detail_includes_submit_confirmation_modal(self):
        _login_with_org(self.client, self.student, self.organization)
        response = self.client.get(reverse("assignments:assignment_detail", kwargs={"pk": self.assignment.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "courseActionConfirmModal")
        self.assertContains(response, "Bu sərbəst işi göndərmək istədiyinizə əminsiniz?")


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
        self.organization = Organization.objects.create(
            name="Assignment Regression Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)

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

    def _login_teacher(self):
        _login_with_org(self.client, self.teacher, self.organization)

    def _login_student(self):
        _login_with_org(self.client, self.student, self.organization)

    def test_assignment_views_render_existing_submission_using_user_relation(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="Existing answer",
            status="submitted",
        )

        self._login_student()

        detail_response = self.client.get(reverse("assignments:assignment_detail", kwargs={"pk": self.assignment.id}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(list(detail_response.context["user_submissions"]), [submission])

        my_submissions_response = self.client.get(reverse("assignments:my_submissions", kwargs={"pk": self.assignment.id}))
        self.assertEqual(my_submissions_response.status_code, 200)
        self.assertEqual(list(my_submissions_response.context["submissions"]), [submission])

    def test_submit_assignment_stores_uploaded_file_in_json_payload(self):
        self._login_student()

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

        self._login_teacher()
        response = self.client.get(
            reverse("assignments:review_assignment_submissions", kwargs={"pk": self.assignment.id}),
            {"submission": str(submission.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_submission_id"], str(submission.id))
        self.assertContains(response, "results-filter-card")
        self.assertContains(response, "resultsFilterSearchInput")

    def test_review_submissions_renders_bulk_delete_controls_for_teacher(self):
        Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="Delete me",
            status="submitted",
        )

        self._login_teacher()
        response = self.client.get(reverse("assignments:review_assignment_submissions", kwargs={"pk": self.assignment.id}))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_delete_submissions"])
        self.assertContains(response, "selectedAssignmentCount")
        self.assertContains(response, "deleteSelectedAssignmentsBtn")
        self.assertContains(response, "js-assignment-submission-checkbox")

    def test_review_submissions_hides_student_name_for_first_five_minutes_then_reveals(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="Anonymous answer",
            status="submitted",
        )

        self._login_teacher()
        response = self.client.get(reverse("assignments:review_assignment_submissions", kwargs={"pk": self.assignment.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonim tələbə")
        self.assertContains(response, "Yoxla")
        self.assertNotContains(response, self.student.username)
        self.assertNotContains(response, 'data-review-countdown="')

        # Pending (submitted) submissions remain anonymous regardless of elapsed time —
        # the teacher sees the student name only after grading AND the re-check window closes.
        submission.submitted_at = timezone.now() - timedelta(minutes=6)
        submission.save(update_fields=["submitted_at"])

        still_anonymous_response = self.client.get(
            reverse("assignments:review_assignment_submissions", kwargs={"pk": self.assignment.id})
        )
        self.assertEqual(still_anonymous_response.status_code, 200)
        self.assertContains(still_anonymous_response, "Anonim tələbə")
        self.assertNotContains(still_anonymous_response, self.student.username)

    def test_review_submissions_shows_recheck_then_view_after_window_closes(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="Recheck answer",
            status="graded",
            grade="91.50",
            feedback="Initial grading",
            graded_at=timezone.now(),
        )

        self._login_teacher()
        response = self.client.get(reverse("assignments:review_assignment_submissions", kwargs={"pk": self.assignment.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yenidən yoxla")
        self.assertContains(response, "Anonim tələbə")
        self.assertContains(response, 'data-review-countdown="')
        self.assertEqual(response.context["submissions"][0].review_action_label, "Yenidən yoxla")

        submission.graded_at = timezone.now() - timedelta(minutes=6)
        submission.save(update_fields=["graded_at"])

        locked_response = self.client.get(reverse("assignments:review_assignment_submissions", kwargs={"pk": self.assignment.id}))
        self.assertEqual(locked_response.status_code, 200)
        self.assertContains(locked_response, "Bax")
        self.assertContains(locked_response, self.student.username)
        self.assertEqual(locked_response.context["submissions"][0].review_action_label, "Bax")

    def test_review_submissions_includes_confirm_modal_and_preserves_grade_value(self):
        submission = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="Grade value answer",
            status="graded",
            grade="20.00",
            feedback="Saved assignment score",
            graded_at=timezone.now(),
        )

        self._login_teacher()
        response = self.client.get(
            reverse("assignments:review_assignment_submissions", kwargs={"pk": self.assignment.id}),
            {"submission": str(submission.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "courseActionConfirmModal")
        self.assertContains(response, 'id="grade-input"')
        self.assertContains(response, 'step="1"')
        self.assertContains(response, 'data-grade="20"')

    def test_delete_assignment_submissions_removes_selected_rows(self):
        first = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="First delete",
            status="submitted",
        )
        second = Submission.objects.create(
            assignment=self.assignment,
            user=self.student,
            content="Second delete",
            status="submitted",
        )

        self._login_teacher()
        response = self.client.post(
            reverse("assignments:delete_assignment_submissions", kwargs={"pk": self.assignment.id}),
            {
                "submission_ids": [str(first.id), str(second.id)],
                "next": reverse("assignments:review_assignment_submissions", kwargs={"pk": self.assignment.id}),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Submission.objects.filter(id=first.id).exists())
        self.assertFalse(Submission.objects.filter(id=second.id).exists())

    def test_student_submit_then_teacher_grade_flow_hides_results_until_review_window_closes(self):
        self._login_student()

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

        self._login_teacher()
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

        self._login_student()
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


class RosterAPIAuthorizationTest(TestCase):
    """Test authorization for roster API endpoints"""

    def setUp(self):
        self.client = Client()

        # Create users
        self.owner = User.objects.create_user("owner", "owner@example.com", "StrongPass123!")
        self.teacher = User.objects.create_user("teacher", "teacher@example.com", "StrongPass123!")
        self.assistant = User.objects.create_user("assistant", "assistant@example.com", "StrongPass123!")
        self.student = User.objects.create_user("student", "student@example.com", "StrongPass123!")
        self.unauthorized_user = User.objects.create_user("unauthorized", "unauthorized@example.com", "StrongPass123!")

        self.organization = Organization.objects.create(
            name="Assignment Roster Org",
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
        self.course = Course.objects.create(owner=self.owner, title="Test Course", status="published")

        # Add memberships
        CourseMembership.objects.create(course=self.course, user=self.teacher, role="teacher")
        CourseMembership.objects.create(course=self.course, user=self.assistant, role="assistant")
        CourseMembership.objects.create(course=self.course, user=self.student, role="student", group_name="Group A")

    def _login_as(self, user):
        _login_with_org(self.client, user, self.organization)

    def test_search_students_owner_can_access(self):
        """Course owner should be able to search students"""
        self._login_as(self.owner)
        response = self.client.get(reverse("assignments:search_students"), {"course_id": self.course.id, "q": "student"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())

    def test_search_students_teacher_can_access(self):
        """Teacher should be able to search students"""
        self._login_as(self.teacher)
        response = self.client.get(reverse("assignments:search_students"), {"course_id": self.course.id, "q": "student"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())

    def test_search_students_assistant_can_access(self):
        """Assistant should be able to search students"""
        self._login_as(self.assistant)
        response = self.client.get(reverse("assignments:search_students"), {"course_id": self.course.id, "q": "student"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())

    def test_search_students_unauthorized_denied(self):
        """Unauthorized user should be denied"""
        self._login_as(self.unauthorized_user)
        response = self.client.get(reverse("assignments:search_students"), {"course_id": self.course.id, "q": "student"})
        self.assertEqual(response.status_code, 403)

    def test_search_groups_owner_can_access(self):
        """Course owner should be able to search groups"""
        self._login_as(self.owner)
        response = self.client.get(reverse("assignments:search_groups"), {"course_id": self.course.id, "q": "Group"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())

    def test_search_groups_teacher_can_access(self):
        """Teacher should be able to search groups"""
        self._login_as(self.teacher)
        response = self.client.get(reverse("assignments:search_groups"), {"course_id": self.course.id, "q": "Group"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())

    def test_search_groups_unauthorized_denied(self):
        """Unauthorized user should be denied"""
        self._login_as(self.unauthorized_user)
        response = self.client.get(reverse("assignments:search_groups"), {"course_id": self.course.id, "q": "Group"})
        self.assertEqual(response.status_code, 403)

    def test_students_by_groups_owner_can_access(self):
        """Course owner should be able to get students by groups"""
        self._login_as(self.owner)
        response = self.client.get(reverse("assignments:students_by_groups"), {"course_id": self.course.id, "groups": "Group A"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("students", response.json())

    def test_students_by_groups_teacher_can_access(self):
        """Teacher should be able to get students by groups"""
        self._login_as(self.teacher)
        response = self.client.get(reverse("assignments:students_by_groups"), {"course_id": self.course.id, "groups": "Group A"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("students", response.json())

    def test_students_by_groups_unauthorized_denied(self):
        """Unauthorized user should be denied"""
        self._login_as(self.unauthorized_user)
        response = self.client.get(reverse("assignments:students_by_groups"), {"course_id": self.course.id, "groups": "Group A"})
        self.assertEqual(response.status_code, 403)
