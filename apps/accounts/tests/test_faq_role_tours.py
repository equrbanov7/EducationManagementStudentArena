"""A role tour belongs to an active role in the current tenant."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.accounts.views.profile.faq import faq_page
from apps.accounts.views.profile.faq_tours import tour_catalog, tour_key, tour_roles


class RoleTourTests(SimpleTestCase):
    def setUp(self):
        self.org = SimpleNamespace(pk=9)
        self.user = SimpleNamespace(is_authenticated=True, is_active=True, is_superuser=False)
        self.request = SimpleNamespace(user=self.user, organization=self.org)

    def membership(self, name, org, active=True):
        return SimpleNamespace(
            organization_id=org, role=SimpleNamespace(name=name, organization_id=org, is_active=active)
        )

    def test_other_tenant_and_inactive_roles_do_not_grant_tours(self):
        members = [
            self.membership("student", 9),
            self.membership("chair_head", 11),
            self.membership("rim_staff", 9, False),
        ]
        with patch("apps.accounts.views.profile.faq_editor_catalog.memberships", return_value=members):
            self.assertEqual(tour_roles(self.request), ("telebe",))

    def test_direct_links_obey_the_same_role_scope_as_search(self):
        student_tour = tour_catalog()["telebe"]
        allowed = set(student_tour["sections"])
        caps = {f: True for f in (*student_tour.get("required_flags", ()), "tour_member_telebe")}
        student = faq_page({"faq_guide": "tour-telebe"}, allowed, caps)
        self.assertEqual([g.key for g in student["page"]], ["tour-telebe"])
        self.assertFalse(list(faq_page({"faq_guide": "tour-rehber"}, allowed, caps)["page"]))
        self.assertFalse(list(faq_page({"faq_guide": "laborant-journal"}, allowed, caps)["page"]))
        self.assertFalse(list(faq_page({"faq_guide": "tour-telebe"}, allowed - {"my-journal"}, caps)["page"]))

    def test_each_menu_link_points_at_a_recorded_chapter(self):
        from apps.accounts.views.profile.faq_catalog import media_metadata

        for role, item in tour_catalog().items():
            chapters = media_metadata()[tour_key(role)]["chapters"]
            menu = {c["section"]: c["title"] for c in chapters if c.get("menu")}
            self.assertEqual(menu, item["sections"], role)
            self.assertIn("dashboard", menu, role)
            self.assertIn("faq", menu, role)

    def test_each_published_role_has_an_independent_tour(self):
        from apps.accounts.views.profile.faq_catalog import GUIDES, media_metadata

        role_guides = {g.key: g for g in GUIDES if g.key.startswith("tour-")}
        keys = {tour_key(role) for role in tour_catalog()}
        self.assertEqual(set(role_guides), keys)
        self.assertEqual({k for k in media_metadata() if k.startswith("tour-")}, keys)
        for role in tour_catalog():
            self.assertEqual(role_guides[tour_key(role)].flags, ("tour_member_" + role,))

    def test_system_settings_group_has_its_own_chapter(self):
        from apps.accounts.views.profile.faq_catalog import media_metadata

        for role in ("ikt_rehber", "rehber"):
            sections = tour_catalog()[role]["sections"]
            chapters = {c["section"]: c for c in media_metadata()[tour_key(role)]["chapters"] if c.get("menu")}
            subgroup = chapters["system-settings-journal"]
            self.assertEqual(sections["system-settings-journal"], subgroup["title"])
            self.assertNotEqual(subgroup["start"], chapters["system-settings"]["start"])
