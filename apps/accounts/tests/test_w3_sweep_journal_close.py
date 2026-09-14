"""W3 `w3sweep` (2026-09-14): «Jurnal bağlama» — fakültə əhatəsi `next`-də qalır.

Brauzer süpürgəsi (qa.ikt_rehber): əhatə «Fakültə → X» seçilib önizləmə
yenilənəndən sonra «bağla»/«aç» formalarının `next`-i yalnız `jc_year` + `period`
daşıyırdı; POST-dan sonra RİM «Bütün universitet» görünüşünə düşürdü.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


@override_settings(UNIVERSITY_MODE=True)
class JournalCloseNextKeepsScopeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("w3jc_owner", "w3jc_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="W3JC Univ",
                slug="w3jc-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="w3jc-f", unit_type=OrgUnitType.FACULTY
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
            cls.rim = User.objects.create_user("w3jc_rim", "w3jc_rim@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.rim,
                organization=cls.org,
                role=cls.org.roles.get(name="ikt_rehber"),
                is_primary=True,
                is_active=True,
            )

    def _client(self):
        client = Client()
        client.force_login(self.rim)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _section(self, resp):
        return resp.context["journal_close_section"]

    def test_next_keeps_faculty_scope_and_unit(self):
        resp = self._client().get(
            reverse("accounts:profile"),
            {
                "section": "journal-close",
                "jc_year": "2024/2025",
                "period": str(self.period.id),
                "jc_scope": "faculty",
                "jc_unit": str(self.faculty.id),
            },
        )
        self.assertEqual(resp.status_code, 200)
        next_url = self._section(resp)["post_next_url"]
        self.assertIn("section=journal-close", next_url)
        self.assertIn(f"period={self.period.id}", next_url)
        self.assertIn("jc_scope=faculty", next_url)
        self.assertIn(f"jc_unit={self.faculty.id}", next_url)
        self.assertContains(resp, f'name="next" value="{escape(next_url)}"')

    def test_next_without_unit_has_no_scope_params(self):
        """Bütün universitet (və ya yad/yanlış unit) → `next` əvvəlki kimi qısa."""
        resp = self._client().get(
            reverse("accounts:profile"),
            {"section": "journal-close", "jc_scope": "faculty", "jc_unit": "00000000-0000-0000-0000-000000000000"},
        )
        self.assertEqual(resp.status_code, 200)
        next_url = self._section(resp)["post_next_url"]
        self.assertNotIn("jc_scope", next_url)
        self.assertNotIn("jc_unit", next_url)
