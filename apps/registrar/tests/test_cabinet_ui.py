"""Tests for the student "Fənlərim" (my-subjects) cabinet section (U2-UI-b).

Three layers:
* the ``build_student_subjects_context`` public builder (shape + graceful
  empty state),
* RBAC gating (``my-subjects`` only for students in ``UNIVERSITY_MODE``),
* a full integration GET through the profile view against the seeded demo
  tenant (credit bar, elective, and the absence-barred badge all render).
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.accounts.views._helpers.rbac import _role_capabilities
from apps.organizations.models import Organization
from apps.registrar.public import build_student_subjects_context
from core.rls import bypass_rls

User = get_user_model()


class BuildStudentSubjectsContextTest(TestCase):
    """The public builder degrades gracefully and returns the expected shape."""

    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, user):
        request = self.factory.get("/accounts/profile/?section=my-subjects")
        request.user = user
        return request

    def test_no_organization_returns_empty_state(self):
        user = User.objects.create_user("cab_u0", "cab_u0@qku.edu.az", "pw")
        ctx = build_student_subjects_context(self._request(user), organization=None)
        section = ctx["student_subjects_section"]
        self.assertFalse(section["has_record"])
        self.assertEqual(section["subjects"], [])

    def test_student_without_record_returns_empty_state(self):
        owner = User.objects.create_user("cab_owner", "cab_owner@qku.edu.az", "pw")
        with bypass_rls():
            org = Organization.objects.create(
                name="Cab Univ", slug="cab-univ", org_type="university", owner=owner, status="active", is_active=True
            )
        student = User.objects.create_user("cab_s0", "cab_s0@qku.edu.az", "pw")
        ctx = build_student_subjects_context(self._request(student), organization=org)
        self.assertFalse(ctx["student_subjects_section"]["has_record"])


@override_settings(UNIVERSITY_MODE=True)
class MySubjectsRbacGatingTest(TestCase):
    """``my-subjects`` is a university-mode student section."""

    def _student(self):
        user = User.objects.create_user("rbac_s", "rbac_s@qku.edu.az", "pw")
        profile = user.profile
        profile.role = "student"
        profile.save(update_fields=["role"])
        return user, profile

    def test_student_gets_my_subjects_in_university_mode(self):
        user, profile = self._student()
        caps = _role_capabilities(user, profile)
        self.assertTrue(caps["is_student"])
        self.assertIn("my-subjects", caps["allowed_sections"])

    @override_settings(UNIVERSITY_MODE=False)
    def test_non_university_mode_hides_my_subjects(self):
        user, profile = self._student()
        caps = _role_capabilities(user, profile)
        self.assertNotIn("my-subjects", caps["allowed_sections"])


@override_settings(UNIVERSITY_MODE=True)
class StudentSubjectsCabinetIntegrationTest(TestCase):
    """Full profile-view render of the cabinet against the seeded demo tenant."""

    PASSWORD = "DemoPass123!"

    @classmethod
    def setUpTestData(cls):
        out = StringIO()
        call_command(
            "seed_western_caspian",
            "--password",
            cls.PASSWORD,
            no_first_login_flow=True,
            stdout=out,
            verbosity=0,
        )
        with bypass_rls():
            cls.org = Organization.objects.get(slug="qerbi-kaspi-universiteti")

    def _login(self, username):
        user = User.objects.get(username=username)
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _get_section(self, username):
        client = self._login(username)
        return client.get(reverse("accounts:profile") + "?section=my-subjects")

    def test_student_sees_credit_bar_and_elective(self):
        resp = self._get_section("wcu_student_az1")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("my-subjects", resp.context["allowed_sections"])
        section = resp.context["student_subjects_section"]
        self.assertTrue(section["has_record"])
        # MATH101 marked COMPLETED in the seed → earned credits on the bar.
        self.assertGreater(section["credit_summary"]["earned"], 0)
        # Credit progress card + the AZ group's elective (EL-WEB) are rendered.
        self.assertContains(resp, "credit-progress-card")
        self.assertContains(resp, "EL-WEB")

    def test_absence_barred_student_shows_block_badge(self):
        # wcu_student_az1's CS101 is pushed over the 25% absence limit in the seed.
        resp = self._get_section("wcu_student_az1")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "subject-card--barred")
        barred = [row for row in resp.context["student_subjects_section"]["subjects"] if row["eligibility"]["barred"]]
        self.assertTrue(barred, "expected at least one absence-barred subject")
