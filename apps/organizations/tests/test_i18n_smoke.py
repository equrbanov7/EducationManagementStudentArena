"""I18n smoke tests for organizations pages."""

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import TestCase
from django.urls import reverse
from django.utils import formats, translation
from django.utils.timezone import localtime

from core.constants import OrganizationType, OrgUnitType, RoleScopeType

from ..models import Membership, Organization, OrgUnit, Role
from ..signals import create_default_roles

User = get_user_model()


class OrganizationI18nSmokeTest(TestCase):
    """Basic smoke coverage for organizations page localization."""

    LANGUAGES = ["az", "en", "ru", "tr"]

    def setUp(self):
        # Avoid default-role signal noise for deterministic fixtures.
        post_save.disconnect(create_default_roles, sender=Organization)

        self.user = User.objects.create_user(
            username="i18n_smoke_user",
            email="i18n-smoke@example.com",
            password="testpass123",
        )

        self.organization = Organization.objects.create(
            name="I18N Smoke University",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.user,
        )

        self.role = Role.objects.create(
            organization=self.organization,
            name="admin",
            display_name="Admin",
            level=95,
            scope_type=RoleScopeType.ORGANIZATION,
            permissions=["*"],
            is_active=True,
        )

        self.membership = Membership.objects.create(
            user=self.user,
            organization=self.organization,
            role=self.role,
            is_primary=True,
            is_active=True,
        )

        OrgUnit.objects.create(
            organization=self.organization,
            name="Engineering",
            unit_type=OrgUnitType.FACULTY,
            slug="engineering",
        )

        self.client.force_login(self.user)

        slug = self.organization.slug
        self.routes = [
            reverse("organizations:select"),
            reverse("organizations:dashboard", kwargs={"slug": slug}),
            reverse("organizations:structure", kwargs={"slug": slug}),
            reverse("organizations:members", kwargs={"slug": slug}),
            reverse("organizations:roles", kwargs={"slug": slug}),
            reverse("organizations:settings", kwargs={"slug": slug}),
        ]

    def tearDown(self):
        post_save.connect(create_default_roles, sender=Organization)

    def _get(self, url, lang):
        return self.client.get(url, HTTP_ACCEPT_LANGUAGE=lang)

    def test_pages_render_successfully_in_all_languages(self):
        for lang in self.LANGUAGES:
            for url in self.routes:
                response = self._get(url, lang)
                self.assertEqual(response.status_code, 200, f"Failed for {lang} {url}")
                self.assertIn(f'lang="{lang}"', response.content.decode("utf-8", errors="ignore"))

    def test_localized_org_unit_labels_and_member_date(self):
        expected = {
            "az": {"org": "Universitet", "unit": "Fakültə"},
            "en": {"org": "University", "unit": "Faculty"},
            "ru": {"org": "Университет", "unit": "Факультет"},
            "tr": {"org": "Üniversite", "unit": "Fakülte"},
        }

        for lang in self.LANGUAGES:
            select_response = self._get(reverse("organizations:select"), lang)
            self.assertContains(select_response, expected[lang]["org"])

            structure_response = self._get(
                reverse("organizations:structure", kwargs={"slug": self.organization.slug}),
                lang,
            )
            self.assertContains(structure_response, expected[lang]["unit"])

            members_response = self._get(
                reverse("organizations:members", kwargs={"slug": self.organization.slug}),
                lang,
            )
            with translation.override(lang):
                expected_date = formats.date_format(
                    localtime(self.membership.created_at),
                    "SHORT_DATE_FORMAT",
                    use_l10n=True,
                )
            self.assertContains(members_response, expected_date)
