"""Profil SPA bölmə fraqmenti — YALNIZ öz partial-ını qaytarmalıdır (Faza 7).

Əvvəl bu endpoint tam profil view-ini çağırıb BÜTÜN səhifəni (navbar, sidebar,
footer və ~90 asset teqi) render edir, JSON-a bükür və frontend oradan bir DOM
node-u çıxarırdı — yəni hər bölmə dəyişməsində tam səhifə render olunurdu.
Endpoint-in öz şərhi bunu müvəqqəti geri düşmə kimi qeyd etmişdi.

Bu testlər həmin regressiyanın qayıtmamasını qoruyur: fraqmentdə səhifə
«xrom»u (``<html>``, sidebar, asset teqləri) OLMAMALIDIR, panel node-u isə
OLMALIDIR — frontend məhz onu çıxarır.
"""

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()

PASSWORD = "StrongPass123!"


class ProfileSectionFragmentTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("fr_owner", "fr_owner@qku.edu.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Fragment Univ",
            slug="fragment-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name="teacher",
            defaults={
                "display_name": "Teacher",
                "level": 60,
                "scope_type": RoleScopeType.ORGANIZATION,
                "permissions": [],
                "is_system": False,
                "is_active": True,
            },
        )
        cls.teacher = User.objects.create_user("fr_teacher", "fr_teacher@qku.edu.az", PASSWORD)
        Membership.objects.create(user=cls.teacher, organization=cls.org, role=role, is_primary=True, is_active=True)

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _fragment(self, section="my-exams"):
        response = self.client.get(reverse("accounts:profile_section_fragment", args=[section]))
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    def test_fragment_contains_the_panel_node(self):
        """Frontend müqaviləsi: `[data-profile-section-panel="<section>"]`."""
        payload = self._fragment()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["section"], "my-exams")
        self.assertIn('data-profile-section-panel="my-exams"', payload["html"])
        self.assertEqual(payload["extract_selector"], '[data-profile-section-panel="my-exams"]')

    def test_fragment_does_not_render_the_whole_page(self):
        payload = self._fragment()
        html = payload["html"]

        for chrome in ("<!DOCTYPE", "<html", "</body>", 'id="profileSidebar"'):
            with self.subTest(chrome=chrome):
                self.assertNotIn(chrome, html)

    def test_fragment_carries_no_asset_tags(self):
        """~90 CSS/JS teqi hər swap-da təkrar göndərilməməlidir."""
        html = self._fragment()["html"]

        self.assertNotIn('rel="stylesheet"', html)
        self.assertNotIn("/static/vendor/", html)

    def test_fragment_is_much_smaller_than_the_full_page(self):
        full = self.client.get(reverse("accounts:profile") + "?section=my-exams")
        self.assertEqual(full.status_code, 200)

        fragment_html = self._fragment()["html"]

        # Nisbət konservativdir: ölçmədə 93% azalma alınıb, test 60%-ə bağlanır
        # ki, məzmun böyüyəndə kövrək olmasın.
        self.assertLess(
            len(fragment_html),
            len(full.content) * 0.4,
            f"fraqment {len(fragment_html)} bayt, tam səhifə {len(full.content)} bayt",
        )

    def test_forbidden_section_is_rejected(self):
        response = self.client.get(reverse("accounts:profile_section_fragment", args=["superadmin-users"]))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(json.loads(response.content)["ok"])
