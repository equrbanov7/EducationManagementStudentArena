"""
Characterization tests for the ``dashboard.py`` + ``_dashboard_helpers.py``
refactor (P1.2 + P1.3).

These tests pin the CURRENT entry-point behavior of the dashboard views:
authentication gates, legacy redirects and the teacher-only grading gate.

Deep behavior of the views and the ``_collect_*`` selectors is already covered
by ``test_profile_views.py`` (AssignedItemsViewTest, MyResultsViewTest,
PendingAnswersViewTest, GradingQueueViewTest, PendingReviewViewTest,
ReviewResultsViewTest, StudentDashboardAssignmentVisibilityTest). This file
focuses on the view dispatch contract and the helpers package's public API.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _make_org(name, slug, owner, *, org_type=OrganizationType.SCHOOL):
    return Organization.objects.create(
        name=name,
        slug=slug,
        org_type=org_type,
        owner=owner,
        status="active",
        is_active=True,
    )


def _assign_user_to_org(user, organization, profile_role, *, membership_role_name=None):
    membership_role_name = membership_role_name or {
        ProfileRole.TEACHER: "teacher",
        ProfileRole.STUDENT: "student",
        ProfileRole.MEMBER: "member",
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


class DashboardHelpersPublicApiTest(TestCase):
    """The _dashboard_helpers package must keep its public collector functions."""

    def test_collector_functions_importable(self):
        from apps.accounts.views import _dashboard_helpers

        for name in [
            "_collect_assigned_tasks",
            "_collect_my_results",
            "_collect_pending_answer_items",
            "_collect_pending_review_items",
            "_collect_evaluated_review_items",
        ]:
            self.assertTrue(
                hasattr(_dashboard_helpers, name),
                f"_dashboard_helpers is missing {name} after refactor",
            )


class DashboardDispatchTest(TestCase):
    """Pin the dashboard() legacy redirect."""

    def setUp(self):
        self.client = Client()

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_dashboard_redirects_student_to_profile_cabinet(self):
        student = User.objects.create_user(username="dash_student", email="ds@example.com", password="pw12345678")
        student.profile.role = ProfileRole.STUDENT
        student.profile.save(update_fields=["role", "updated_at"])
        self.client.force_login(student)
        resp = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:profile"))

    def test_dashboard_redirects_teacher_to_profile_cabinet(self):
        admin = User.objects.create_superuser(username="dash_teacher", email="dt@example.com", password="pw12345678")
        self.client.force_login(admin)
        resp = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:profile"))


class TeacherDashboardTest(TestCase):
    """Pin teacher_dashboard view behavior."""

    def setUp(self):
        self.client = Client()

    def test_requires_login(self):
        resp = self.client.get(reverse("accounts:teacher_dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_non_teacher_redirected_to_profile(self):
        student = User.objects.create_user(username="td_student", email="tds@example.com", password="pw12345678")
        student.profile.role = ProfileRole.STUDENT
        student.profile.save(update_fields=["role", "updated_at"])
        self.client.force_login(student)
        resp = self.client.get(reverse("accounts:teacher_dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:profile"))

    def test_teacher_dashboard_redirects_to_profile(self):
        admin = User.objects.create_superuser(username="td_teacher", email="tdt@example.com", password="pw12345678")
        self.client.force_login(admin)
        resp = self.client.get(reverse("accounts:teacher_dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("accounts:profile"))


class StudentDashboardTest(TestCase):
    """Pin student_dashboard view behavior."""

    def setUp(self):
        self.client = Client()

    def test_requires_login(self):
        resp = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_student_renders_200(self):
        student = User.objects.create_user(username="sd_student", email="sds@example.com", password="pw12345678")
        self.client.force_login(student)
        resp = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(resp.status_code, 200)


class GradingQueueTest(TestCase):
    """Pin grading_queue view behavior."""

    def setUp(self):
        self.client = Client()

    def test_requires_login(self):
        resp = self.client.get(reverse("accounts:grading_queue"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_non_teacher_redirected_home(self):
        student = User.objects.create_user(username="gq_student", email="gqs@example.com", password="pw12345678")
        student.profile.role = ProfileRole.STUDENT
        student.profile.save(update_fields=["role", "updated_at"])
        self.client.force_login(student)
        resp = self.client.get(reverse("accounts:grading_queue"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("home"))

    def test_teacher_renders_200(self):
        admin = User.objects.create_superuser(username="gq_teacher", email="gqt@example.com", password="pw12345678")
        self.client.force_login(admin)
        resp = self.client.get(reverse("accounts:grading_queue"))
        self.assertEqual(resp.status_code, 200)


class ResultViewsLoginGateTest(TestCase):
    """Pin the login gate on the result/review views."""

    def setUp(self):
        self.client = Client()

    def test_assigned_exams_requires_login(self):
        resp = self.client.get(reverse("accounts:assigned_exams"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_assigned_courses_requires_login(self):
        resp = self.client.get(reverse("accounts:assigned_courses"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_my_results_requires_login(self):
        resp = self.client.get(reverse("accounts:my_results"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_pending_answers_requires_login(self):
        resp = self.client.get(reverse("accounts:pending_answers"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_pending_review_requires_login(self):
        resp = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_review_results_requires_login(self):
        resp = self.client.get(reverse("accounts:review_results"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp.url)

    def test_pending_review_redirects_non_teacher(self):
        student = User.objects.create_user(username="pr_student", email="prs@example.com", password="pw12345678")
        student.profile.role = ProfileRole.STUDENT
        student.profile.save(update_fields=["role", "updated_at"])
        self.client.force_login(student)
        resp = self.client.get(reverse("accounts:pending_review"))
        self.assertEqual(resp.status_code, 302)
