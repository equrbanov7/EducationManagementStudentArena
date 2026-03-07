"""
View tests for labs app.
"""

from datetime import timedelta
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.courses.models import Course
from apps.labs.models import Lab, LabAssignment, LabSubmission
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class LabDetailBackUrlTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("lab_teacher", "lab_teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("lab_student", "lab_student@example.com", "StrongPass123!")
        self.course = Course.objects.create(owner=self.teacher, title="Lab Course", status="published")
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

    def test_lab_detail_defaults_back_to_course_dashboard(self):
        self.client.login(username="lab_student", password="StrongPass123!")
        response = self.client.get(reverse("labs:lab_detail", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["back_url"],
            reverse("courses:course_dashboard", kwargs={"course_id": self.course.id}),
        )

    def test_lab_detail_returns_to_assigned_tasks_when_opened_from_profile_tasks(self):
        self.client.login(username="lab_student", password="StrongPass123!")
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

        self.client.login(username="lab_student", password="StrongPass123!")
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

        self.client.login(username="lab_teacher", password="StrongPass123!")
        response = self.client.get(reverse("labs:lab_submissions", kwargs={"pk": self.lab.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "answers-stat-grid")
        self.assertContains(response, "answers-table-card__header")


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


class LabReviewVisibilityTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("lab_visibility_teacher", "lvt@example.com", "StrongPass123!")
        self.student = User.objects.create_user("lab_visibility_student", "lvs@example.com", "StrongPass123!")
        self.student.profile.role = ProfileRole.STUDENT
        self.student.profile.save(update_fields=["role", "updated_at"])

        self.course = Course.objects.create(owner=self.teacher, title="Lab Visibility Course", status="published")
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
        self.client.force_login(self.student)

        hidden_response = self.client.get(reverse("labs:lab_detail", kwargs={"pk": self.lab.id}))
        self.assertEqual(hidden_response.status_code, 200)
        self.assertFalse(hidden_response.context["show_review_data"])
        self.assertNotContains(hidden_response, "17.25")
        self.assertContains(hidden_response, 'data-review-countdown="')

        hidden_answers_response = self.client.get(reverse("labs:my_lab_answers", kwargs={"pk": self.lab.id}))
        self.assertEqual(hidden_answers_response.status_code, 200)
        self.assertContains(hidden_answers_response, 'id="reviewCountdown"')
        self.assertNotContains(hidden_answers_response, "17,25")

        self.submission.graded_at = timezone.now() - timedelta(minutes=6)
        self.submission.save(update_fields=["graded_at"])

        visible_response = self.client.get(reverse("labs:lab_detail", kwargs={"pk": self.lab.id}))
        self.assertEqual(visible_response.status_code, 200)
        self.assertTrue(visible_response.context["show_review_data"])
        self.assertContains(visible_response, "17,25")
