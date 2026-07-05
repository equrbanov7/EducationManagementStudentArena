"""U16 — kabinet modul görünürlüyü: superadmin aç/bağla paneli testləri."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.organizations import cabinet_modules
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()


@override_settings(UNIVERSITY_MODE=True)
class CabinetModulesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("cm_owner", "cm_owner@qku.edu.az", "pw")
        cls.superadmin = User.objects.create_user(
            "cm_super", "cm_super@qku.edu.az", "pw", is_superuser=True, is_staff=True
        )
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="CM Univ",
                slug="cm-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.teacher = User.objects.create_user("cm_teacher", "cm_teacher@qku.edu.az", "pw")
            cls.student = User.objects.create_user("cm_student", "cm_student@qku.edu.az", "pw")
            for user, role in ((cls.teacher, "teacher"), (cls.student, "student")):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
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

    # ── Servis qatı ──────────────────────────────────────────────────────────
    def test_posts_disabled_by_default(self):
        with bypass_rls():
            self.assertFalse(cabinet_modules.is_module_enabled(self.org, "posts"))
            self.assertTrue(cabinet_modules.is_module_enabled(self.org, "journal"))
            self.assertIn("posts", cabinet_modules.disabled_sections(self.org))

    def test_toggle_persists_in_settings(self):
        with bypass_rls():
            cabinet_modules.set_module_enabled(self.org, "posts", True)
            self.org.refresh_from_db()
            self.assertTrue(cabinet_modules.is_module_enabled(self.org, "posts"))
            cabinet_modules.set_module_enabled(self.org, "posts", False)
            self.org.refresh_from_db()
            self.assertFalse(cabinet_modules.is_module_enabled(self.org, "posts"))

    # ── Rbac / sidebar tətbiqi ───────────────────────────────────────────────
    def test_teacher_does_not_see_posts_section(self):
        page = self._client(self.teacher).get(reverse("accounts:profile")).content.decode()
        self.assertNotIn('data-section="posts"', page)
        self.assertNotIn('data-section="create-post"', page)

    def test_superadmin_still_sees_posts(self):
        page = self._client(self.superadmin).get(reverse("accounts:profile")).content.decode()
        self.assertIn('data-section="posts"', page)

    def test_disabled_module_removes_sidebar_and_fragment(self):
        # Jurnal modulunu söndür → müəllim sidebar-da görmür, fragment 403.
        with bypass_rls():
            cabinet_modules.set_module_enabled(self.org, "journal", False)
        client = self._client(self.teacher)
        page = client.get(reverse("accounts:profile")).content.decode()
        self.assertNotIn('data-section="my-journal"', page)
        fragment = client.get(reverse("accounts:profile_section_fragment", kwargs={"section": "my-journal"}))
        self.assertEqual(fragment.status_code, 403)
        # Superadmin yenə görür.
        supage = self._client(self.superadmin).get(reverse("accounts:profile")).content.decode()
        self.assertIn('data-section="my-journal"', supage)

    def test_disabled_module_hidden_from_search_nav(self):
        import json

        with bypass_rls():
            cabinet_modules.set_module_enabled(self.org, "schedule", False)
        resp = self._client(self.student).get(reverse("accounts:global_search"), {"q": ""})
        titles = [i["title"] for g in json.loads(resp.content)["groups"] for i in g["items"]]
        self.assertNotIn("Dərs cədvəli", titles)

    # ── Superadmin panel endpoint-i ─────────────────────────────────────────
    def test_superadmin_endpoint_toggles_module(self):
        client = self._client(self.superadmin)
        resp = client.post(
            reverse("accounts:superadmin_organizations"),
            {
                "action": "set_cabinet_module",
                "organization_id": str(self.org.id),
                "module_key": "posts",
                "enabled": "1",
                "next": reverse("accounts:profile") + "?section=superadmin-org-features",
            },
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.org.refresh_from_db()
            self.assertTrue(cabinet_modules.is_module_enabled(self.org, "posts"))

    def test_search_nav_targets_open_in_shell(self):
        import json

        resp = self._client(self.student).get(reverse("accounts:global_search"), {"q": ""})
        urls = [i["url"] for g in json.loads(resp.content)["groups"] for i in g["items"]]
        for url in urls:
            self.assertIn("?section=", url, f"standalone URL axtarışda qalıb: {url}")
