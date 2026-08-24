"""U12 — registrar kabinet bölmələri profil shell-inin içində (SPA panel) testləri."""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


@override_settings(UNIVERSITY_MODE=True)
class RegistrarProfileSectionsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ps_owner", "ps_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="PS Univ",
                slug="ps-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="ps-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.teacher = User.objects.create_user("ps_teacher", "ps_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("ps_student", "ps_student@qku.edu.az", "pw")
            cls.dean = User.objects.create_user("ps_dean", "ps_dean@qku.edu.az", "pw")
            cls.hr_user = User.objects.create_user("ps_hr", "ps_hr@qku.edu.az", "pw")
            for user, role in (
                (cls.teacher, "teacher"),
                (cls.student, "student"),
                (cls.dean, "dean"),
                (cls.hr_user, "hr"),
            ):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    scope_unit=cls.group if role == "dean" else None,
                    is_primary=True,
                    is_active=True,
                )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _fragment(self, user, section):
        return self._client(user).get(reverse("accounts:profile_section_fragment", kwargs={"section": section}))

    # ── Full-page ?section= renders inside the shell ─────────────────────────
    def test_student_schedule_section_renders_in_shell(self):
        resp = self._client(self.student).get(reverse("accounts:profile"), {"section": "my-schedule"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-profile-section-panel="my-schedule"')
        self.assertContains(resp, "sgx-weekpills")  # mockup: Bu həftə / Gələn həftə pilləri
        self.assertContains(resp, "profile-sidebar")  # sidebar stays

    def test_calendar_section_renders(self):
        resp = self._client(self.student).get(reverse("accounts:profile"), {"section": "academic-calendar"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-profile-section-panel="academic-calendar"')
        self.assertContains(resp, "acal-timeline")

    def test_teacher_journal_section_renders(self):
        resp = self._client(self.teacher).get(reverse("accounts:profile"), {"section": "my-journal"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-profile-section-panel="my-journal"')

    def test_dean_gets_analytics_and_approvals_sections(self):
        for section in ("analytics", "grade-approvals"):
            resp = self._client(self.dean).get(reverse("accounts:profile"), {"section": section})
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, f'data-profile-section-panel="{section}"')

    # ── AJAX fragment API respects role gating ───────────────────────────────
    def test_fragment_api_returns_schedule_for_student(self):
        resp = self._fragment(self.student, "my-schedule")
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content)
        self.assertTrue(payload["ok"])
        self.assertIn('data-profile-section-panel="my-schedule"', payload["html"])

    def test_fragment_api_denies_analytics_to_student(self):
        resp = self._fragment(self.student, "analytics")
        self.assertEqual(resp.status_code, 403)

    def test_fragment_api_allows_journal_to_student(self):
        """Yenidən-dizayn: tələbə öz jurnal xülasəsini profil panelində görür."""
        resp = self._fragment(self.student, "my-journal")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(json.loads(resp.content)["ok"])

    def test_fragment_api_allows_analytics_to_dean(self):
        resp = self._fragment(self.dean, "analytics")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(json.loads(resp.content)["ok"])

    def test_org_scoped_view_unit_role_has_matching_nav_and_view_access(self):
        page = self._client(self.hr_user).get(reverse("accounts:profile"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'data-section="analytics"')

        fragment = self._fragment(self.hr_user, "analytics")
        self.assertEqual(fragment.status_code, 200)
        self.assertTrue(json.loads(fragment.content)["ok"])

    # ── Sidebar shows the Universitet group links per role ───────────────────
    def test_sidebar_links_per_role(self):
        student_page = self._client(self.student).get(reverse("accounts:profile")).content.decode()
        self.assertIn('data-section="my-schedule"', student_page)
        self.assertIn('data-section="academic-calendar"', student_page)
        self.assertNotIn('data-section="analytics"', student_page)
        # Tələbə: jurnal SPA bölmə kimi açılır (öz xülasəsi).
        self.assertIn('data-section="my-journal"', student_page)

        # Müəllim: jurnal iş sahəsi yeni tabda ayrıca URL-də açılır.
        teacher_page = self._client(self.teacher).get(reverse("accounts:profile")).content.decode()
        self.assertNotIn('data-section="my-journal"', teacher_page)
        self.assertIn('href="/jurnal/" target="_blank"', teacher_page)

        dean_page = self._client(self.dean).get(reverse("accounts:profile")).content.decode()
        self.assertIn('data-section="analytics"', dean_page)
        self.assertIn('data-section="grade-approvals"', dean_page)
