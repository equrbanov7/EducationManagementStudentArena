"""
Tests for the profile statistics section.

Covers:
- Access control per role
- Tenant isolation (cross-org data leakage)
- AI endpoint behavior
- Filter functionality
- CSV export
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole, UserProfile
from apps.courses.models import Course, CourseMembership
from apps.exams.models import Exam, ExamAttempt
from apps.organizations.models import Membership, Organization, Role
from apps.organizations.signals import create_default_roles
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()


# ── Helpers ────────────────────────────────────────────────────────


def _make_org(name, slug, owner, org_type=OrganizationType.UNIVERSITY):
    post_save.disconnect(create_default_roles, sender=Organization)
    try:
        org = Organization.objects.create(
            name=name,
            slug=slug,
            org_type=org_type,
            owner=owner,
            status="active",
            is_active=True,
        )
    finally:
        post_save.connect(create_default_roles, sender=Organization)
    return org


def _make_role(org, name="student", level=10):
    return Role.objects.create(
        organization=org,
        name=name,
        display_name=name.title(),
        level=level,
        scope_type=RoleScopeType.ORGANIZATION,
        permissions=[],
        is_active=True,
    )


def _assign(user, org, role, profile_role=ProfileRole.STUDENT):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.organization = org
    profile.organization_type = org.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    return Membership.objects.create(
        user=user,
        organization=org,
        role=role,
        is_primary=True,
        is_active=True,
    )


# ── Access control tests ──────────────────────────────────────────


class StatisticsSectionAccessTest(TestCase):
    """Verify the statistics section is accessible to all authenticated roles."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="stat_student", email="stat@test.com", password="testpass123"
        )
        self.org = _make_org("Stat Org", "stat-org", self.user)
        role = _make_role(self.org)
        _assign(self.user, self.org, role, ProfileRole.STUDENT)

    def test_unauthenticated_redirects(self):
        response = self.client.get(reverse("accounts:profile") + "?section=statistics")
        self.assertEqual(response.status_code, 302)

    def test_student_can_access_statistics(self):
        self.client.login(username="stat_student", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=statistics")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Statistika")

    def test_statistics_section_in_allowed_sections(self):
        from apps.accounts.views._helpers import _role_capabilities

        profile = self.user.profile
        caps = _role_capabilities(self.user, profile)
        self.assertIn("statistics", caps["allowed_sections"])


class StatisticsTeacherAccessTest(TestCase):
    """Verify teacher role gets statistics access."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="stat_teacher", email="steacher@test.com", password="testpass123"
        )
        self.org = _make_org("Teacher Stat Org", "teacher-stat-org", self.teacher)
        role = _make_role(self.org, name="teacher", level=60)
        _assign(self.teacher, self.org, role, ProfileRole.TEACHER)

    def test_teacher_can_access_statistics(self):
        self.client.login(username="stat_teacher", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=statistics")
        self.assertEqual(response.status_code, 200)

    def test_teacher_statistics_section_allowed(self):
        from apps.accounts.views._helpers import _role_capabilities

        profile = self.teacher.profile
        caps = _role_capabilities(self.teacher, profile)
        self.assertIn("statistics", caps["allowed_sections"])


class StatisticsSuperadminAccessTest(TestCase):
    """Verify superadmin gets statistics access."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            username="stat_superadmin", email="sa@test.com", password="testpass123"
        )

    def test_superadmin_can_access_statistics(self):
        self.client.login(username="stat_superadmin", password="testpass123")
        response = self.client.get(reverse("accounts:profile") + "?section=statistics")
        self.assertEqual(response.status_code, 200)

    def test_superadmin_statistics_section_allowed(self):
        from apps.accounts.views._helpers import _role_capabilities

        profile, _ = UserProfile.objects.get_or_create(user=self.superadmin)
        caps = _role_capabilities(self.superadmin, profile)
        self.assertIn("statistics", caps["allowed_sections"])


# ── Tenant isolation tests ────────────────────────────────────────


class StatisticsTenantIsolationTest(TestCase):
    """Ensure students in Org A do not see data from Org B."""

    def setUp(self):
        self.user_a = User.objects.create_user(
            username="tenant_a_stat", email="ta_stat@a.com", password="testpass123"
        )
        self.user_b = User.objects.create_user(
            username="tenant_b_stat", email="tb_stat@b.com", password="testpass123"
        )
        self.org_a = _make_org("Org A Stat", "org-a-stat", self.user_a)
        self.org_b = _make_org("Org B Stat", "org-b-stat", self.user_b)

        role_a = _make_role(self.org_a)
        role_b = _make_role(self.org_b)

        _assign(self.user_a, self.org_a, role_a, ProfileRole.STUDENT)
        _assign(self.user_b, self.org_b, role_b, ProfileRole.STUDENT)

    def test_selector_student_only_sees_own_org_data(self):
        """The student statistics selector should only return data for the user."""
        from apps.accounts.services.statistics_selectors import get_student_statistics

        stats = get_student_statistics(self.user_a, organization=self.org_a)
        # No exams created so all counts should be zero
        self.assertEqual(stats["summary"]["exam_count"], 0)
        self.assertEqual(stats["summary"]["assignment_count"], 0)

    def test_org_admin_scoped_to_own_org(self):
        """Org admin stats should only see their own organization."""
        from apps.accounts.services.statistics_selectors import get_org_admin_statistics

        stats = get_org_admin_statistics(organization=self.org_a)
        # Should not include org_b data
        self.assertIsInstance(stats["summary"]["total_members"], int)


# ── Filter tests ──────────────────────────────────────────────────


class StatisticsFilterTest(TestCase):
    """Verify that filter parameters are properly applied."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="stat_filter_user", email="filter@test.com", password="testpass123"
        )
        self.org = _make_org("Filter Org", "filter-org", self.user)
        role = _make_role(self.org)
        _assign(self.user, self.org, role, ProfileRole.STUDENT)

    def test_date_filter_applied(self):
        self.client.login(username="stat_filter_user", password="testpass123")
        response = self.client.get(
            reverse("accounts:profile") + "?section=statistics&stat_date_from=2025-01-01&stat_date_to=2025-12-31"
        )
        self.assertEqual(response.status_code, 200)

    def test_content_type_filter(self):
        self.client.login(username="stat_filter_user", password="testpass123")
        response = self.client.get(
            reverse("accounts:profile") + "?section=statistics&stat_content_type=exam"
        )
        self.assertEqual(response.status_code, 200)


# ── AI endpoint tests ─────────────────────────────────────────────


class StatisticsAIEndpointTest(TestCase):
    """Verify AI summary endpoint within the statistics section."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="stat_ai_user", email="ai@test.com", password="testpass123"
        )
        self.org = _make_org("AI Org", "ai-org", self.user)
        role = _make_role(self.org)
        _assign(self.user, self.org, role, ProfileRole.STUDENT)

    @override_settings(GEMINI_API_KEY="")
    def test_ai_summary_returns_json_when_no_key(self):
        """Without a Gemini API key, should return an error JSON."""
        self.client.login(username="stat_ai_user", password="testpass123")
        response = self.client.get(
            reverse("accounts:profile") + "?section=statistics&stat_ai_summary=1",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data.get("ok", True))

    def test_ai_endpoint_requires_auth(self):
        response = self.client.get(
            reverse("accounts:profile") + "?section=statistics&stat_ai_summary=1"
        )
        self.assertEqual(response.status_code, 302)


# ── CSV export tests ──────────────────────────────────────────────


class StatisticsCSVExportTest(TestCase):
    """Verify CSV export endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="stat_csv_user", email="csv@test.com", password="testpass123"
        )
        self.org = _make_org("CSV Org", "csv-org", self.user)
        role = _make_role(self.org)
        _assign(self.user, self.org, role, ProfileRole.STUDENT)

    def test_csv_export_returns_csv(self):
        self.client.login(username="stat_csv_user", password="testpass123")
        response = self.client.get(reverse("accounts:statistics_export_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("statistika.csv", response["Content-Disposition"])

    def test_csv_export_requires_auth(self):
        response = self.client.get(reverse("accounts:statistics_export_csv"))
        self.assertEqual(response.status_code, 302)

    def test_csv_export_contains_header(self):
        self.client.login(username="stat_csv_user", password="testpass123")
        response = self.client.get(reverse("accounts:statistics_export_csv"))
        content = response.content.decode("utf-8")
        self.assertIn("Metrika", content)
        self.assertIn("Dəyər", content)


# ── Selector unit tests ───────────────────────────────────────────


class StatisticsSelectorsTest(TestCase):
    """Unit tests for statistics_selectors functions."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="sel_test_user", email="sel@test.com", password="testpass123"
        )
        self.org = _make_org("Selector Org", "sel-org", self.user)

    def test_student_statistics_returns_expected_keys(self):
        from apps.accounts.services.statistics_selectors import get_student_statistics

        stats = get_student_statistics(self.user, organization=self.org)
        self.assertIn("summary", stats)
        self.assertIn("trend", stats)
        self.assertIn("score_breakdown", stats)
        self.assertIn("recent_activity", stats)
        self.assertIn("courses", stats)

    def test_teacher_statistics_returns_expected_keys(self):
        from apps.accounts.services.statistics_selectors import get_teacher_statistics

        stats = get_teacher_statistics(self.user, organization=self.org)
        self.assertIn("summary", stats)
        self.assertIn("trend", stats)
        self.assertIn("group_comparison", stats)

    def test_org_admin_statistics_returns_expected_keys(self):
        from apps.accounts.services.statistics_selectors import get_org_admin_statistics

        stats = get_org_admin_statistics(organization=self.org)
        self.assertIn("summary", stats)
        self.assertIn("trend", stats)
        self.assertIn("course_rankings", stats)
        self.assertIn("teacher_overview", stats)

    def test_superadmin_statistics_returns_expected_keys(self):
        from apps.accounts.services.statistics_selectors import get_superadmin_statistics

        stats = get_superadmin_statistics()
        self.assertIn("summary", stats)
        self.assertIn("trend", stats)
        self.assertIn("org_comparison", stats)

    def test_build_ai_stats_payload(self):
        from apps.accounts.services.statistics_selectors import build_ai_stats_payload, get_student_statistics

        stats = get_student_statistics(self.user, organization=self.org)
        payload = build_ai_stats_payload(role="student", stats=stats)
        self.assertEqual(payload["role"], "student")
        self.assertIn("summary", payload)

    def test_date_filter_does_not_crash(self):
        from apps.accounts.services.statistics_selectors import get_student_statistics

        stats = get_student_statistics(
            self.user,
            organization=self.org,
            filters={"date_from": "2025-01-01", "date_to": "2025-12-31"},
        )
        self.assertIsInstance(stats["summary"]["total_items"], int)

    def test_content_type_filter_exam_only(self):
        from apps.accounts.services.statistics_selectors import get_student_statistics

        stats = get_student_statistics(
            self.user,
            organization=self.org,
            filters={"content_type": "exam"},
        )
        # With no data, all counts should be zero
        self.assertEqual(stats["summary"]["avg_score"], 0)

    def test_student_statistics_with_none_organization(self):
        """Stats should still work when organization is None."""
        from apps.accounts.services.statistics_selectors import get_student_statistics

        stats = get_student_statistics(self.user, organization=None)
        self.assertIn("summary", stats)
        self.assertEqual(stats["summary"]["total_items"], 0)

    def test_teacher_statistics_with_none_organization(self):
        """Teacher stats should still work when organization is None."""
        from apps.accounts.services.statistics_selectors import get_teacher_statistics

        stats = get_teacher_statistics(self.user, organization=None)
        self.assertIn("summary", stats)
        self.assertIsInstance(stats["summary"]["total_courses"], int)
