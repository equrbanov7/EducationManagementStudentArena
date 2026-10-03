"""«Sistem tənzimləmələri» (sahib 2026-10-03): RİM rəhbəri limitləri bir yerdən dəyişir.

Kilidlənən qaydalar:

* sətir yoxdursa mühitin / kodun defoltu işləyir; yararsız saxlanmış dəyər tətbiq olunmur;
* yazmaq yalnız RİM rəhbəri (``ikt_rehber``) və superadmin — dekan 403 alır, bölmə ona görünmür;
* hədd xaricindəki dəyər rədd olunur, dəyişməyən sahə yoxlanmır, «standarta qaytar» sətri silir, audit yazılır;
* dəyər real yerlərdə tətbiq olunur: giriş limiti, OTP müddəti, jurnal pəncərəsi, AI modeli;
* DB trigger-i q/b pəncərəsini eyni açardan oxuyur (registrar 0084).
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import RuntimeSetting
from apps.accounts.services import runtime_settings_admin
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, Organization, Role
from core import runtime_settings as rs
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "runtime-settings"}}


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class RuntimeSettingsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("rs_owner", "rs_owner@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name="RS Univ", slug="rs-univ", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active"
        )

        def member(username, role_name, level):
            role, _ = Role.objects.update_or_create(
                organization=cls.org,
                name=role_name,
                defaults={
                    "display_name": role_name,
                    "level": level,
                    "scope_type": RoleScopeType.ORGANIZATION,
                    "permissions": ["semester.view"],
                    "is_active": True,
                },
            )
            user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
            Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
            return user

        cls.rim = member("rs_rim", "ikt_rehber", 95)
        cls.dean = member("rs_dean", "dean", 80)

    def setUp(self):
        RuntimeSetting.objects.all().delete()
        rs.invalidate()

    def tearDown(self):
        rs.invalidate()

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_defaults_overrides_and_invalid_values(self):
        self.assertEqual(rs.get("journal.lesson_edit_hours"), 2)
        self.assertIsNone(rs.override("journal.lesson_edit_hours"))
        RuntimeSetting.objects.create(key="journal.lesson_edit_hours", value=5)
        RuntimeSetting.objects.create(key="journal.mark_edit_hours", value=999)  # hədd xaricində — tətbiq olunmur
        rs.invalidate()
        self.assertEqual(rs.get("journal.lesson_edit_hours"), 5)
        self.assertEqual(rs.get("journal.mark_edit_hours"), 2)
        with override_settings(RUNTIME_SETTINGS_ENABLED=False):
            self.assertEqual(rs.get("journal.lesson_edit_hours"), 2)

    def test_values_reach_the_real_code_paths(self):
        from apps.accounts.views.auth._shared import _login_account_rate_limit
        from apps.registrar import gradebook
        from core.ai_models import preferred_model, resolve_chain
        from core.utils import get_auth_otp_expiry_seconds

        runtime_settings_admin.save_values(
            actor=self.rim,
            data={
                "login.account_rate.count": "40",
                "login.account_rate.window": "60",
                "otp.expiry_minutes": "10",
                "journal.lesson_edit_hours": "4",
                "journal.mark_edit_hours": "6",
                "ai.model": "gemini-3.5-flash-lite",
            },
        )
        self.assertEqual(_login_account_rate_limit(), "40/60m")
        self.assertEqual(get_auth_otp_expiry_seconds(), 600)
        self.assertEqual(gradebook.lesson_edit_window(), timedelta(hours=4))
        self.assertEqual(gradebook.mark_edit_window(), timedelta(hours=6))
        self.assertEqual(preferred_model(), "gemini-3.5-flash-lite")
        self.assertEqual(resolve_chain(("gemini-3.8-flash",))[0], "gemini-3.5-flash-lite")

    def test_validation_reset_unchanged_and_audit(self):
        with self.assertRaises(runtime_settings_admin.RuntimeSettingsError) as ctx:
            runtime_settings_admin.save_values(actor=self.rim, data={"otp.max_attempts": "999"})
        self.assertIn("otp.max_attempts", ctx.exception.errors)

        result = runtime_settings_admin.save_values(
            actor=self.rim, data={"otp.max_attempts": "8", "journal.lesson_edit_hours": "2"}  # ikincisi dəyişməyib
        )
        self.assertEqual([item["key"] for item in result["changed"]], ["otp.max_attempts"])
        self.assertTrue(RuntimeSetting.objects.filter(key="otp.max_attempts", value=8).exists())
        self.assertTrue(AuditLog.objects.filter(resource_type="core.runtime_settings").exists())

        default = str(rs.SPECS["otp.max_attempts"].default())
        runtime_settings_admin.save_values(actor=self.rim, data={"otp.max_attempts": default})
        self.assertFalse(RuntimeSetting.objects.filter(key="otp.max_attempts").exists())

    def test_only_rim_head_sees_section_and_can_save(self):
        url = reverse("accounts:system_settings_save")
        denied = self._client(self.dean).post(url, {"journal.lesson_edit_hours": "5"})
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(RuntimeSetting.objects.exists())

        allowed = self._client(self.rim).post(
            url, data='{"journal.lesson_edit_hours": "5"}', content_type="application/json"
        )
        self.assertEqual(allowed.status_code, 200, allowed.content)
        self.assertTrue(RuntimeSetting.objects.filter(key="journal.lesson_edit_hours", value=5).exists())

        dean_sections = self._client(self.dean).get(reverse("accounts:profile")).context["allowed_sections"]
        rim_sections = self._client(self.rim).get(reverse("accounts:profile")).context["allowed_sections"]
        self.assertNotIn("system-settings", dean_sections)
        self.assertIn("system-settings", rim_sections)

        fragment = self._client(self.rim).get(
            reverse("accounts:profile_section_fragment", kwargs={"section": "system-settings"})
        )
        self.assertEqual(fragment.status_code, 200)
        groups = fragment.context["system_settings_section"]["groups"]
        self.assertEqual({group["key"] for group in groups}, {"login", "otp", "session", "journal", "ai", "exam"})

    def test_mark_trigger_reads_the_same_key(self):
        if connection.vendor != "postgresql":
            self.skipTest("Postgres trigger")
        with connection.cursor() as cursor:
            cursor.execute("SELECT prosrc FROM pg_proc WHERE proname = 'registrar_journal_mark_guard'")
            source = cursor.fetchone()[0]
        self.assertIn("journal.mark_edit_hours", source)
        self.assertIn("accounts_runtimesetting", source)
