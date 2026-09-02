"""«Müraciətlərim» kabinet bölməsi — görünürlük, fraqment, badge.

Bölmə SAHİB tələbi ilə UNİVERSALDIR: aktiv üzvlüyü olan hər rol (tələbə,
müəllim, əməkdaş, koordinator, dekan, RİM) sidebar-da onu görür və AJAX
fraqmenti 200 qaytarır. Aktiv üzvlüyü OLMAYAN istifadəçidə bənd YOXDUR
(fail-closed) — testlər məhz bu iki ucu bağlayır.

Domen məntiqi ``apps/applications/tests``-də yoxlanılır; burada YALNIZ kabinet
inteqrasiyası var (bölmə açarı, sidebar bəndi, badge açarı, panel markup-u).
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.applications.tests.factories import make_world

User = get_user_model()

SECTION = "applications"
PANEL = 'data-profile-section-panel="applications"'
BADGE_KEY = 'data-badge-key="applications_pending_count"'


@override_settings(UNIVERSITY_MODE=True)
class ApplicationsSectionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.world = make_world("apx-ui")
        cls.org = cls.world["organization"]

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _fragment(self, user):
        return self._client(user).get(
            reverse("accounts:profile_section_fragment", kwargs={"section": SECTION}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    # ── Fraqment hər ailə üçün 200 ───────────────────────────────────────
    def test_fragment_renders_for_every_family(self):
        for key in ("student", "teacher", "coordinator", "rim", "dean", "chair_head"):
            with self.subTest(role=key):
                response = self._fragment(self.world[key])
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["section"], SECTION)
                self.assertIn(PANEL, payload["html"])

    def test_fragment_carries_the_json_endpoints_and_rules(self):
        payload = self._fragment(self.world["student"]).json()
        self.assertIn('data-url-list="/muracietler/api/list/"', payload["html"])
        self.assertIn('data-url-create="/muracietler/api/create/"', payload["html"])
        self.assertIn('data-min-subject="5"', payload["html"])
        self.assertIn('data-min-body="20"', payload["html"])
        self.assertIn('data-min-note="10"', payload["html"])
        # JS mətn kataloqu json_script ilə gəlir (xarici .js template-dən keçmir).
        self.assertIn('id="apx-i18n"', payload["html"])

    # ── Ailəyə görə budaqlanma (bir şablon, bir view) ────────────────────
    def test_sender_sees_the_create_button_and_handler_does_not(self):
        student = self._fragment(self.world["student"]).json()["html"]
        self.assertIn("data-apx-open-create", student)
        self.assertIn("Tələbə kabineti", student)

        coordinator = self._fragment(self.world["coordinator"]).json()["html"]
        self.assertIn('data-apx-tab="inbox"', coordinator)
        self.assertIn('data-apx-tab="watching"', coordinator)
        self.assertIn("şöbəyə gələn müraciətlər", coordinator)

    def test_handler_who_can_also_create_gets_the_mine_tab(self):
        html = self._fragment(self.world["coordinator"]).json()["html"]
        self.assertIn('data-apx-tab="mine"', html)
        self.assertIn("data-apx-open-create", html)

    # ── Sidebar bəndi + badge ────────────────────────────────────────────
    def test_sidebar_shows_the_item_with_the_badge_key(self):
        for key in ("student", "teacher", "coordinator", "rim"):
            with self.subTest(role=key):
                response = self._client(self.world[key]).get(reverse("accounts:profile"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'data-section="applications"')
                self.assertContains(response, "Müraciətlərim")
                self.assertContains(response, BADGE_KEY)

    def test_badges_api_exposes_the_applications_key(self):
        response = self._client(self.world["coordinator"]).get(reverse("accounts:profile_badges_api"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("applications_pending_count", response.json()["badges"])

    # ── Fail-closed: icazəsiz / üzvlüksüz istifadəçi ─────────────────────
    def test_member_without_application_permissions_has_no_item(self):
        response = self._client(self.world["outsider"]).get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-section="applications"')

    def test_user_without_membership_has_no_item_and_no_fragment(self):
        stranger = User.objects.create_user("apx-stranger", "apx-stranger@example.test", "pw12345!")
        client = Client()
        client.force_login(stranger)
        page = client.get(reverse("accounts:profile"))
        self.assertNotContains(page, 'data-section="applications"')

        fragment = client.get(
            reverse("accounts:profile_section_fragment", kwargs={"section": SECTION}),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(fragment.status_code, 403)

    # ── «Təyin et» dialoqunun namizəd endpoint-i ─────────────────────────
    def test_assignees_endpoint_is_empty_without_an_application(self):
        response = self._client(self.world["coordinator"]).get(reverse("accounts:applications_assignees"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "results": []})
