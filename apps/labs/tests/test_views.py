"""
View tests for labs app.
"""

from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.labs.models import Lab, LabAnswer, LabAssignment, LabBlock, LabQuestion, LabSubmission
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


class LabDetailBackUrlTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("lab_teacher", "lab_teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("lab_student", "lab_student@example.com", "StrongPass123!")
        self.organization = Organization.objects.create(
            name="Lab Detail Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)
        self.course = Course.objects.create(owner=self.teacher, title="Lab Course", status="published")
        CourseMembership.objects.create(course=self.course, user=self.student, role="student")
        self.lab = Lab.objects.create(
            course=self.course,
            title="Lab Back Url",
            description="Lab back url test",
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(days=1),
            max_score=100,
            max_attempts=1,
            status="published",
            created_by=self.teacher,
        )

    def _login_as(self, user):
        _login_with_org(self.client, user, self.organization)

    def test_lab_detail_defaults_back_to_course_dashboard(self):
        self._login_as(self.student)
        response = self.client.get(reverse("labs:lab_detail", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["back_url"],
            reverse("courses:course_dashboard", kwargs={"course_id": self.course.id}),
        )

    def test_lab_detail_returns_to_assigned_tasks_when_opened_from_profile_tasks(self):
        self._login_as(self.student)
        response = self.client.get(
            reverse("labs:lab_detail", kwargs={"pk": self.lab.id}),
            {"from_section": "assigned-exams", "assigned_type": "labs"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["back_url"],
            f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type=labs",
        )

    def test_my_lab_answers_uses_back_url_with_return_to(self):
        assignment = LabAssignment.get_or_create_for_student(self.lab, self.student)
        LabSubmission.objects.create(
            assignment=assignment,
            status="submitted",
            attempt_number=1,
        )

        self._login_as(self.student)
        return_to = f"{reverse('accounts:profile')}?section=assigned-courses"
        response = self.client.get(
            reverse("labs:my_lab_answers", kwargs={"pk": self.lab.id}),
            {"return_to": return_to},
        )

        self.assertEqual(response.status_code, 200)
        expected_back_url = f"{reverse('courses:course_dashboard', kwargs={'course_id': self.course.id})}?{urlencode({'return_to': return_to})}"
        self.assertEqual(response.context["back_url"], expected_back_url)
        self.assertContains(response, expected_back_url)

    def test_lab_submissions_uses_shared_answers_workspace_layout(self):
        assignment = LabAssignment.get_or_create_for_student(self.lab, self.student)
        LabSubmission.objects.create(
            assignment=assignment,
            status="submitted",
            attempt_number=1,
        )

        self._login_as(self.teacher)
        response = self.client.get(reverse("labs:lab_submissions", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "results-summary")
        self.assertContains(response, "results-filter-card")
        self.assertContains(response, "selectedLabCount")

    def test_lab_detail_renders_finish_confirmation_modal(self):
        LabAssignment.get_or_create_for_student(self.lab, self.student)
        block = LabBlock.objects.create(lab=self.lab, title="Block 1", order=1)
        LabQuestion.objects.create(block=block, question_text="Question 1", question_number=1, points=10)

        self._login_as(self.student)
        response = self.client.get(reverse("labs:lab_detail", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="finishLabConfirmModal"')
        self.assertContains(response, 'id="confirmFinishLabBtn"')
        self.assertContains(response, "Bitirməyə əminsiniz?")

    def test_lab_submissions_support_bulk_delete_controls(self):
        assignment = LabAssignment.get_or_create_for_student(self.lab, self.student)
        LabSubmission.objects.create(
            assignment=assignment,
            status="submitted",
            attempt_number=1,
        )

        self._login_as(self.teacher)
        response = self.client.get(reverse("labs:lab_submissions", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_delete_submissions"])
        self.assertContains(response, "deleteSelectedLabsBtn")
        self.assertContains(response, "js-lab-submission-checkbox")

    def test_delete_lab_submissions_removes_selected_rows(self):
        assignment = LabAssignment.get_or_create_for_student(self.lab, self.student)
        first = LabSubmission.objects.create(
            assignment=assignment,
            status="submitted",
            attempt_number=1,
        )
        second = LabSubmission.objects.create(
            assignment=assignment,
            status="late",
            attempt_number=2,
        )

        self._login_as(self.teacher)
        response = self.client.post(
            reverse("labs:delete_submissions", kwargs={"pk": self.lab.id}),
            {
                "submission_ids": [str(first.id), str(second.id)],
                "next": reverse("labs:lab_submissions", kwargs={"pk": self.lab.id}),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(LabSubmission.objects.filter(id=first.id).exists())
        self.assertFalse(LabSubmission.objects.filter(id=second.id).exists())


class LabTenantIsolationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher_a = User.objects.create_user("lab_tenant_teacher_a", "lta@example.com", "StrongPass123!")
        self.teacher_b = User.objects.create_user("lab_tenant_teacher_b", "ltb@example.com", "StrongPass123!")
        self.student_a = User.objects.create_user("lab_tenant_student_a", "lsa@example.com", "StrongPass123!")
        self.student_b = User.objects.create_user("lab_tenant_student_b", "lsb@example.com", "StrongPass123!")

        self.org_a = Organization.objects.create(
            name="Lab Org A",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher_a,
            status="active",
            is_active=True,
        )
        self.org_b = Organization.objects.create(
            name="Lab Org B",
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

        self.course_a = Course.objects.create(owner=self.teacher_a, title="Lab Course A", status="published")
        self.course_b = Course.objects.create(owner=self.teacher_b, title="Lab Course B", status="published")

        self.lab_b = Lab.objects.create(
            course=self.course_b,
            title="Tenant B Lab",
            description="Tenant B lab",
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(days=1),
            max_score=100,
            max_attempts=1,
            status="published",
            created_by=self.teacher_b,
        )

        self.client.force_login(self.teacher_a)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

    def test_api_get_groups_blocks_cross_tenant_course_id(self):
        response = self.client.get(reverse("labs:api_get_groups", kwargs={"course_id": self.course_b.id}))
        self.assertEqual(response.status_code, 404)

    def test_lab_detail_blocks_cross_tenant_lab_id(self):
        self.client.force_login(self.student_a)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.get(reverse("labs:lab_detail", kwargs={"pk": self.lab_b.id}))
        self.assertEqual(response.status_code, 404)


class LabAccessControlTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user("lab_owner", "lab_owner@example.com", "StrongPass123!")
        self.other_teacher = User.objects.create_user("other_teacher", "other_teacher@example.com", "StrongPass123!")
        self.allowed_student = User.objects.create_user("allowed_student", "allowed_student@example.com", "StrongPass123!")
        self.blocked_student = User.objects.create_user("blocked_student", "blocked_student@example.com", "StrongPass123!")
        self.unenrolled_student = User.objects.create_user("unenrolled_student", "unenrolled_student@example.com", "StrongPass123!")

        self.organization = Organization.objects.create(
            name="Lab Access Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.owner,
            status="active",
            is_active=True,
        )

        _assign_user_to_org(self.owner, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.other_teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.allowed_student, self.organization, ProfileRole.STUDENT)
        _assign_user_to_org(self.blocked_student, self.organization, ProfileRole.STUDENT)
        _assign_user_to_org(self.unenrolled_student, self.organization, ProfileRole.STUDENT)

        self.course = Course.objects.create(owner=self.owner, title="Lab Access Course", status="published")
        CourseMembership.objects.create(course=self.course, user=self.allowed_student, role="student", group_name="A1")
        CourseMembership.objects.create(course=self.course, user=self.blocked_student, role="student", group_name="B1")

        self.lab = Lab.objects.create(
            course=self.course,
            title="Restricted Lab",
            description="Restricted lab test",
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(days=1),
            max_score=100,
            max_attempts=1,
            status="published",
            allowed_groups="A1",
            created_by=self.owner,
        )

    def _login_as(self, user):
        _login_with_org(self.client, user, self.organization)

    def test_lab_detail_blocks_same_tenant_student_without_course_membership(self):
        self._login_as(self.unenrolled_student)

        response = self.client.get(reverse("labs:lab_detail", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(LabAssignment.objects.filter(lab=self.lab, student=self.unenrolled_student).exists())

    def test_lab_detail_blocks_student_outside_allowed_groups_and_students(self):
        self.lab.allowed_students = str(self.owner.id)
        self.lab.save(update_fields=["allowed_students"])
        self._login_as(self.blocked_student)

        response = self.client.get(reverse("labs:lab_detail", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(LabAssignment.objects.filter(lab=self.lab, student=self.blocked_student).exists())

    def test_submit_lab_blocks_student_outside_access_rules(self):
        self._login_as(self.blocked_student)

        response = self.client.post(reverse("labs:submit_lab", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["success"], False)
        self.assertFalse(LabAssignment.objects.filter(lab=self.lab, student=self.blocked_student).exists())

    def test_lab_submissions_blocks_other_teacher_in_same_tenant(self):
        assignment = LabAssignment.get_or_create_for_student(self.lab, self.allowed_student)
        LabSubmission.objects.create(assignment=assignment, status="submitted", attempt_number=1)
        self._login_as(self.other_teacher)

        response = self.client.get(reverse("labs:lab_submissions", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 403)


class LabQuestionImportTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("lab_import_teacher", "lab_import_teacher@example.com", "StrongPass123!")
        self.organization = Organization.objects.create(
            name="Lab Import Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)

        self.course = Course.objects.create(owner=self.teacher, title="Lab Import Course", status="published")
        self.lab = Lab.objects.create(
            course=self.course,
            title="Lab Import",
            description="Lab import test",
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(days=1),
            max_score=100,
            max_attempts=1,
            status="published",
            created_by=self.teacher,
        )
        self.block = LabBlock.objects.create(lab=self.lab, title="Import Block", order=1)

    def test_import_questions_returns_interpolated_success_message(self):
        _login_with_org(self.client, self.teacher, self.organization)

        response = self.client.post(
            reverse("labs:import_questions", kwargs={"block_id": self.block.id}),
            {
                "questions_text": "1. Birinci sual\n2. Ikinci sual",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["count"], 2)
        self.assertNotIn("%(count)s", payload["message"])
        self.assertIn("2", payload["message"])
        self.assertEqual(LabQuestion.objects.filter(block=self.block).count(), 2)


class LabTeacherReviewWindowTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("lab_review_teacher", "lab_review_teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("lab_review_student", "lab_review_student@example.com", "StrongPass123!")
        self.organization = Organization.objects.create(
            name="Lab Teacher Review Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)

        self.course = Course.objects.create(owner=self.teacher, title="Lab Teacher Review Course", status="published")
        CourseMembership.objects.create(course=self.course, user=self.student, role="student", group_name="580")
        self.lab = Lab.objects.create(
            course=self.course,
            title="Lab Teacher Review",
            description="Teacher-side review window test",
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(days=1),
            max_score=100,
            max_attempts=1,
            status="published",
            created_by=self.teacher,
        )
        self.assignment = LabAssignment.objects.create(lab=self.lab, student=self.student)
        self.submission = LabSubmission.objects.create(
            assignment=self.assignment,
            status="graded",
            score="95.00",
            feedback="Teacher review window",
            graded_at=timezone.now(),
            attempt_number=1,
        )
        self.block = LabBlock.objects.create(lab=self.lab, title="Review Block", order=1)
        self.question = LabQuestion.objects.create(
            block=self.block,
            question_text="Explain the solution",
            question_number=1,
            points=100,
        )
        self.answer = LabAnswer.objects.create(
            lab=self.lab,
            question=self.question,
            student=self.student,
            submission=self.submission,
            attempt_number=1,
            answer="Manual total grading answer",
            is_draft=False,
        )

    def _login_teacher(self):
        _login_with_org(self.client, self.teacher, self.organization)

    def test_lab_submissions_hides_student_identity_during_recheck_window(self):
        self._login_teacher()

        response = self.client.get(reverse("labs:lab_submissions", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonim tələbə")
        self.assertContains(response, "Yenidən yoxla")
        self.assertContains(response, 'data-review-countdown="')
        self.assertNotContains(response, self.student.username)
        self.assertNotContains(response, self.student.email)

    def test_lab_submissions_hide_pending_student_identity_for_first_five_minutes(self):
        pending_submission = LabSubmission.objects.create(
            assignment=self.assignment,
            status="submitted",
            attempt_number=2,
        )
        self.submission.graded_at = timezone.now() - timedelta(minutes=6)
        self.submission.save(update_fields=["graded_at"])
        self._login_teacher()

        response = self.client.get(reverse("labs:lab_submissions", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 200)
        submissions = list(response.context["submissions"])
        pending_context = next(sub for sub in submissions if sub.id == pending_submission.id)
        # Pending (submitted) submissions are always anonymous — no countdown timer.
        self.assertFalse(pending_context.can_view_student_identity)
        self.assertEqual(pending_context.identity_window_seconds_left, 0)
        self.assertContains(response, "Anonim tələbə")
        self.assertNotContains(response, 'data-review-countdown="')

    def test_lab_submissions_reveals_student_identity_after_recheck_window_closes(self):
        self.submission.graded_at = timezone.now() - timedelta(minutes=6)
        self.submission.save(update_fields=["graded_at"])
        self._login_teacher()

        response = self.client.get(reverse("labs:lab_submissions", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student.username)
        self.assertContains(response, self.student.email)
        self.assertNotContains(response, "Yenidən yoxla")
        self.assertContains(response, "Bax")
        self.assertNotContains(response, "Yoxlama bağlanıb")
        self.assertNotContains(response, "Blokları idarə et")
        self.assertNotContains(response, 'data-review-countdown="')

    def test_grade_submission_page_preserves_saved_total_in_recheck_window(self):
        self._login_teacher()

        response = self.client.get(reverse("labs:grade_submission_page", kwargs={"pk": self.submission.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="95"')
        self.assertContains(response, 'step="1"')
        self.assertContains(response, "courseActionConfirmModal")
        self.assertNotContains(response, "useManualTotal")
        self.assertContains(response, f'name="answer_score_{self.answer.id}"')

    def test_grade_submission_page_keeps_pending_student_anonymous_for_first_five_minutes(self):
        pending_submission = LabSubmission.objects.create(
            assignment=self.assignment,
            status="submitted",
            attempt_number=2,
        )
        self._login_teacher()

        response = self.client.get(reverse("labs:grade_submission_page", kwargs={"pk": pending_submission.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonim tələbə")
        self.assertContains(response, "Anonim yoxlama pəncərəsi aktivdir.")

    def test_grade_submission_post_preserves_existing_manual_total_without_checkbox(self):
        self._login_teacher()

        response = self.client.post(
            reverse("labs:grade_submission_page", kwargs={"pk": self.submission.id}),
            {
                "score": "95.00",
                "feedback": "Teacher review window updated",
                "use_manual_total": "0",
                f"answer_score_{self.answer.id}": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.submission.refresh_from_db()
        self.answer.refresh_from_db()
        self.assertEqual(self.submission.score, 95)
        self.assertEqual(self.submission.feedback, "Teacher review window updated")
        self.assertIsNone(self.answer.score)

    def test_grade_submission_page_allows_read_only_view_after_window_closes(self):
        self.submission.graded_at = timezone.now() - timedelta(minutes=6)
        self.submission.save(update_fields=["graded_at"])
        self._login_teacher()

        response = self.client.get(reverse("labs:grade_submission_page", kwargs={"pk": self.submission.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student.username)
        self.assertContains(response, "Bu cavab artıq yalnız baxış üçündür.")
        self.assertContains(response, "disabled")
        self.assertContains(response, "Bağla")


class LabReviewVisibilityTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("lab_visibility_teacher", "lvt@example.com", "StrongPass123!")
        self.student = User.objects.create_user("lab_visibility_student", "lvs@example.com", "StrongPass123!")
        self.organization = Organization.objects.create(
            name="Lab Visibility Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)

        self.course = Course.objects.create(owner=self.teacher, title="Lab Visibility Course", status="published")
        CourseMembership.objects.create(course=self.course, user=self.student, role="student")
        self.lab = Lab.objects.create(
            course=self.course,
            title="Lab Visibility",
            description="Lab visibility test",
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(days=1),
            max_score=100,
            max_attempts=1,
            status="published",
            created_by=self.teacher,
        )
        self.assignment = LabAssignment.objects.create(lab=self.lab, student=self.student)
        self.submission = LabSubmission.objects.create(
            assignment=self.assignment,
            status="graded",
            score="17.25",
            feedback="Lab feedback should wait",
            graded_at=timezone.now(),
            attempt_number=1,
        )

    def test_lab_detail_hides_score_until_review_window_closes(self):
        _login_with_org(self.client, self.student, self.organization)

        hidden_response = self.client.get(reverse("labs:lab_detail", kwargs={"pk": self.lab.id}))
        self.assertEqual(hidden_response.status_code, 200)
        self.assertFalse(hidden_response.context["show_review_data"])
        self.assertNotContains(hidden_response, "17.25")
        self.assertContains(hidden_response, 'data-review-countdown="')

        hidden_answers_response = self.client.get(reverse("labs:my_lab_answers", kwargs={"pk": self.lab.id}))
        self.assertEqual(hidden_answers_response.status_code, 200)
        self.assertContains(hidden_answers_response, 'data-bs-target="#viewLabSubmission')
        self.assertContains(hidden_answers_response, 'data-review-countdown="')
        self.assertNotContains(hidden_answers_response, "17,25")
        self.assertContains(hidden_answers_response, "status-review-pending")
        self.assertNotContains(hidden_answers_response, "fa-spin-pulse")

        self.submission.graded_at = timezone.now() - timedelta(minutes=6)
        self.submission.save(update_fields=["graded_at"])

        visible_response = self.client.get(reverse("labs:lab_detail", kwargs={"pk": self.lab.id}))
        self.assertEqual(visible_response.status_code, 200)
        self.assertTrue(visible_response.context["show_review_data"])
        self.assertContains(visible_response, "17,25")


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
            name="Lab Roster Org",
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

    def test_api_get_groups_owner_can_access(self):
        """Course owner should be able to access groups"""
        self._login_as(self.owner)
        response = self.client.get(reverse("labs:api_get_groups", kwargs={"course_id": self.course.id}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("groups", response.json())

    def test_api_get_groups_teacher_can_access(self):
        """Teacher should be able to access groups"""
        self._login_as(self.teacher)
        response = self.client.get(reverse("labs:api_get_groups", kwargs={"course_id": self.course.id}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("groups", response.json())

    def test_api_get_groups_assistant_can_access(self):
        """Assistant should be able to access groups"""
        self._login_as(self.assistant)
        response = self.client.get(reverse("labs:api_get_groups", kwargs={"course_id": self.course.id}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("groups", response.json())

    def test_api_get_groups_unauthorized_denied(self):
        """Unauthorized user should be denied"""
        self._login_as(self.unauthorized_user)
        response = self.client.get(reverse("labs:api_get_groups", kwargs={"course_id": self.course.id}))
        self.assertEqual(response.status_code, 403)

    def test_api_get_students_owner_can_access(self):
        """Course owner should be able to access students"""
        self._login_as(self.owner)
        response = self.client.get(reverse("labs:api_get_students", kwargs={"course_id": self.course.id}), {"groups": "Group A"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("students", response.json())

    def test_api_get_students_teacher_can_access(self):
        """Teacher should be able to access students"""
        self._login_as(self.teacher)
        response = self.client.get(reverse("labs:api_get_students", kwargs={"course_id": self.course.id}), {"groups": "Group A"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("students", response.json())

    def test_api_get_students_assistant_can_access(self):
        """Assistant should be able to access students"""
        self._login_as(self.assistant)
        response = self.client.get(reverse("labs:api_get_students", kwargs={"course_id": self.course.id}), {"groups": "Group A"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("students", response.json())

    def test_api_get_students_unauthorized_denied(self):
        """Unauthorized user should be denied"""
        self._login_as(self.unauthorized_user)
        response = self.client.get(reverse("labs:api_get_students", kwargs={"course_id": self.course.id}), {"groups": "Group A"})
        self.assertEqual(response.status_code, 403)


class LabUploadSecurityTest(TestCase):
    """Tests that all lab upload surfaces pass through the centralized security layer."""

    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("lab_upload_teacher", "lut@example.com", "StrongPass123!")
        self.student = User.objects.create_user("lab_upload_student", "lus@example.com", "StrongPass123!")
        self.organization = Organization.objects.create(
            name="Lab Upload Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)
        self.course = Course.objects.create(owner=self.teacher, title="Lab Upload Course", status="published")
        CourseMembership.objects.create(course=self.course, user=self.student, role="student")
        self.lab = Lab.objects.create(
            course=self.course,
            title="Lab Upload Security",
            description="Upload security test",
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(days=1),
            max_score=100,
            max_attempts=3,
            status="published",
            allow_file_upload=True,
            created_by=self.teacher,
        )
        self.block = LabBlock.objects.create(lab=self.lab, title="Upload Block", order=1)
        self.question = LabQuestion.objects.create(
            block=self.block,
            question_text="Upload test question",
            question_number=1,
            points=10,
        )

    def _login_teacher(self):
        _login_with_org(self.client, self.teacher, self.organization)

    def _login_student(self):
        _login_with_org(self.client, self.student, self.organization)

    # ── auto_save_answer (student file upload) ──────────────────────────

    def test_auto_save_answer_rejects_php_file(self):
        self._login_student()
        response = self.client.post(
            reverse("labs:auto_save_answer", kwargs={"pk": self.lab.id}),
            {
                "question_id": self.question.id,
                "answer": "",
                "answer_file": SimpleUploadedFile("shell.php", b"<?php echo 'pwn';", content_type="application/x-httpd-php"),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(LabAnswer.objects.count(), 0)

    def test_auto_save_answer_rejects_exe_file(self):
        self._login_student()
        response = self.client.post(
            reverse("labs:auto_save_answer", kwargs={"pk": self.lab.id}),
            {
                "question_id": self.question.id,
                "answer": "",
                "answer_file": SimpleUploadedFile(
                    "virus.exe",
                    b"MZ\x00\x00\x00\x00",
                    content_type="application/x-msdownload",
                ),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(LabAnswer.objects.count(), 0)

    def test_auto_save_answer_rejects_html_file(self):
        self._login_student()
        response = self.client.post(
            reverse("labs:auto_save_answer", kwargs={"pk": self.lab.id}),
            {
                "question_id": self.question.id,
                "answer": "",
                "answer_file": SimpleUploadedFile(
                    "xss.html",
                    b"<script>alert(1)</script>",
                    content_type="text/html",
                ),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(LabAnswer.objects.count(), 0)

    def test_auto_save_answer_rejects_double_extension_file(self):
        self._login_student()
        response = self.client.post(
            reverse("labs:auto_save_answer", kwargs={"pk": self.lab.id}),
            {
                "question_id": self.question.id,
                "answer": "",
                "answer_file": SimpleUploadedFile(
                    "shell.php.zip",
                    b"PK\x03\x04",
                    content_type="application/zip",
                ),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(LabAnswer.objects.count(), 0)

    def test_auto_save_answer_randomizes_filename_for_valid_upload(self):
        self._login_student()
        response = self.client.post(
            reverse("labs:auto_save_answer", kwargs={"pk": self.lab.id}),
            {
                "question_id": self.question.id,
                "answer": "my answer",
                "answer_file": SimpleUploadedFile(
                    "submission.pdf",
                    b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n",
                    content_type="application/pdf",
                ),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        lab_answer = LabAnswer.objects.filter(lab=self.lab, student=self.student).first()
        self.assertIsNotNone(lab_answer)
        self.assertTrue(lab_answer.answer_file.name.endswith(".pdf"))
        self.assertNotIn("submission", lab_answer.answer_file.name)

    # ── Teacher file upload via edit_lab ─────────────────────────────────

    def test_edit_lab_teacher_file_rejects_php(self):
        self._login_teacher()
        response = self.client.post(
            reverse("labs:edit_lab", kwargs={"pk": self.lab.id}),
            {
                "title": self.lab.title,
                "description": self.lab.description,
                "start_datetime": self.lab.start_datetime.strftime("%Y-%m-%dT%H:%M"),
                "end_datetime": self.lab.end_datetime.strftime("%Y-%m-%dT%H:%M"),
                "max_score": self.lab.max_score,
                "max_attempts": self.lab.max_attempts,
                "status": self.lab.status,
                "max_file_size_mb": 50,
                "teacher_files": SimpleUploadedFile(
                    "shell.php",
                    b"<?php echo 'pwn';",
                    content_type="application/x-httpd-php",
                ),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_create_question_rejects_php_attachment(self):
        self._login_teacher()
        response = self.client.post(
            reverse("labs:create_question", kwargs={"block_id": self.block.id}),
            {
                "question_text": "What is security?",
                "points": 10,
                "attachment": SimpleUploadedFile(
                    "shell.php",
                    b"<?php echo 'pwn';",
                    content_type="application/x-httpd-php",
                ),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(LabQuestion.objects.filter(block=self.block).count(), 1)

    # ── Additional negative upload scenarios ─────────────────────────────────

    def test_auto_save_answer_rejects_php_jpg_double_extension(self):
        """A file named shell.php.jpg is blocked by the double-extension attack check."""
        self._login_student()
        response = self.client.post(
            reverse("labs:auto_save_answer", kwargs={"pk": self.lab.id}),
            {
                "question_id": self.question.id,
                "answer": "",
                "answer_file": SimpleUploadedFile(
                    "shell.php.jpg",
                    b"\xff\xd8\xff\xe0",
                    content_type="image/jpeg",
                ),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(LabAnswer.objects.count(), 0)

    def test_auto_save_answer_rejects_mime_spoofed_image(self):
        """A file with a .jpg extension but a blocked MIME type is rejected."""
        self._login_student()
        response = self.client.post(
            reverse("labs:auto_save_answer", kwargs={"pk": self.lab.id}),
            {
                "question_id": self.question.id,
                "answer": "",
                "answer_file": SimpleUploadedFile(
                    "image.jpg",
                    b"\xff\xd8\xff\xe0",
                    content_type="application/x-httpd-php",
                ),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(LabAnswer.objects.count(), 0)

    def test_auto_save_answer_rejects_exe_signature_in_pdf(self):
        """A .pdf file containing an MZ (EXE) signature is rejected by the signature check."""
        self._login_student()
        response = self.client.post(
            reverse("labs:auto_save_answer", kwargs={"pk": self.lab.id}),
            {
                "question_id": self.question.id,
                "answer": "",
                "answer_file": SimpleUploadedFile(
                    "document.pdf",
                    b"MZ\x90\x00\x03\x00\x00\x00",
                    content_type="application/pdf",
                ),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(LabAnswer.objects.count(), 0)

    def test_auto_save_answer_rejects_oversized_file(self):
        """A file exceeding the lab's max_file_size_mb limit is rejected."""
        self.lab.max_file_size_mb = 1
        self.lab.save(update_fields=["max_file_size_mb"])
        self._login_student()
        big_content = b"X" * (1 * 1024 * 1024 + 1)
        response = self.client.post(
            reverse("labs:auto_save_answer", kwargs={"pk": self.lab.id}),
            {
                "question_id": self.question.id,
                "answer": "",
                "answer_file": SimpleUploadedFile("bigfile.pdf", big_content, content_type="application/pdf"),
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(LabAnswer.objects.count(), 0)
