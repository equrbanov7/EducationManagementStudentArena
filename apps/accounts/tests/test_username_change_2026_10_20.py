"""2026-10-20 — istifadəçi öz istifadəçi adını «Profil redaktə» bölməsindən dəyişir (sahib).

Yoxlanılır: uğurlu dəyişiklik (sessiya qalır, köhnə ad işləmir, audit + bildiriş + e-poçt), yanlış parol, tutulmuş
ad (hərf registrindən asılı olmayaraq), yararsız format, rezerv adlar, gözləmə müddəti, «Sistem tənzimləmələri»
açarı (söndürüləndə kart gizlənir və POST rədd olunur), cəhd limiti, view-as altında bloklanma.
"""

from __future__ import annotations

from datetime import timedelta

from django.apps import apps
from django.contrib.auth import authenticate, get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.middleware import ViewAsMiddleware
from apps.accounts.services import username_change
from apps.accounts.services.username_change import UsernameChangeError, change_own_username, validate_username
from core import rate_limit as rate_limit_module
from core import runtime_settings

User = get_user_model()
PASSWORD = "StrongPass123!"
EDIT_URL = reverse("accounts:profile") + "?section=edit-profile"


class _Base(TestCase):
    def setUp(self):
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        self.addCleanup(rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear)
        runtime_settings.invalidate()
        self.addCleanup(runtime_settings.invalidate)
        self.user = User.objects.create_user(
            "aysel.quliyeva", "aysel@example.com", PASSWORD, first_name="Aysel", last_name="Quliyeva"
        )
        self.client.force_login(self.user)

    def _post(self, new_username, password=PASSWORD):
        return self.client.post(
            reverse("accounts:profile"),
            {
                "profile_form": "change-username",
                "section": "edit-profile",
                "new_username": new_username,
                "current_password": password,
            },
        )

    def _messages(self, response):
        return [str(message) for message in response.wsgi_request._messages]

    def _username(self):
        self.user.refresh_from_db()
        return self.user.username


class UsernameChangeSuccessTest(_Base):
    def test_success_normalizes_keeps_session_and_old_name_stops_working(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self._post("  Aysel.Q ")

        self.assertRedirects(response, EDIT_URL, fetch_redirect_response=False)
        self.assertEqual(self._username(), "aysel.q")
        self.assertIsNotNone(self.user.profile.username_changed_at)
        self.assertTrue(any("aysel.q" in text for text in self._messages(response)))
        # Sessiya qalır.
        self.assertEqual(self.client.get(EDIT_URL).status_code, 200)
        # Köhnə ad işləmir, yeni ad və e-poçt işləyir.
        self.assertIsNone(authenticate(username="aysel.quliyeva", password=PASSWORD))
        self.assertEqual(authenticate(username="aysel.q", password=PASSWORD), self.user)
        self.assertEqual(authenticate(username="aysel@example.com", password=PASSWORD), self.user)
        # In-app bildiriş + e-poçt.
        notification = apps.get_model("notifications", "InAppNotification").objects.get(recipient=self.user)
        self.assertIn("aysel.quliyeva", notification.message)
        self.assertIn("aysel.q", notification.message)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["aysel@example.com"])
        self.assertIn("RİM", mail.outbox[0].body)

    def test_audit_row_records_old_and_new(self):
        self._post("aysel.new")

        log = apps.get_model("audit", "AuditLog").objects.get(resource_type="Username", resource_id=str(self.user.pk))
        self.assertEqual(log.user_id, self.user.pk)
        self.assertEqual(log.action, "update")
        self.assertEqual(log.old_values, {"username": "aysel.quliyeva"})
        self.assertEqual(log.new_values, {"username": "aysel.new"})

    def test_placeholder_email_gets_no_mail(self):
        User.objects.filter(pk=self.user.pk).update(email="x1@placeholder.invalid")
        with self.captureOnCommitCallbacks(execute=True):
            self._post("aysel.ph")

        self.assertEqual(self._username(), "aysel.ph")
        self.assertEqual(len(mail.outbox), 0)

    def test_edit_page_shows_card_with_current_username(self):
        page = self.client.get(EDIT_URL)

        self.assertContains(page, 'id="usernameChangeCard"')
        self.assertContains(page, 'name="profile_form" value="change-username"')
        self.assertContains(page, "aysel.quliyeva")
        self.assertContains(page, "data-ems-confirm=")


class UsernameChangeRejectTest(_Base):
    def _assert_rejected(self, response, fragment=""):
        self.assertRedirects(response, EDIT_URL, fetch_redirect_response=False)
        self.assertEqual(self._username(), "aysel.quliyeva")
        if fragment:
            self.assertTrue(any(fragment in text for text in self._messages(response)), self._messages(response))

    def test_wrong_password(self):
        self._assert_rejected(self._post("aysel.q", password="yanlis-parol"), "parol")
        self._assert_rejected(self._post("aysel.q", password=""), "parol")
        self.assertFalse(apps.get_model("audit", "AuditLog").objects.filter(resource_type="Username").exists())

    def test_taken_case_insensitive(self):
        User.objects.create_user("Taken.Name", "taken@example.com", PASSWORD)

        self._assert_rejected(self._post("taken.name"), "artıq")
        self._assert_rejected(self._post("TAKEN.NAME"), "artıq")

    def test_same_as_current(self):
        self._assert_rejected(self._post("AYSEL.QULIYEVA"), "fərqli")

    def test_invalid_patterns(self):
        for value in ("ab", "1abc", "ad..soyad", "ad._soyad", "ad.", "_ad", "əli.vəli", "a b c", "ad@x.az", "a" * 31):
            with self.subTest(value=value), self.assertRaises(UsernameChangeError) as ctx:
                validate_username(username_change.normalize_username(value))
            self.assertIn(ctx.exception.code, {"length", "pattern"})
        for value in ("abc", "ad.soyad", "aygun.akbarova.230k", "elvin_q-2", "a" * 30):
            with self.subTest(value=value):
                validate_username(value)
        self._assert_rejected(self._post("ad..soyad"), "latın")

    def test_reserved(self):
        for value in ("admin", "root", "superadmin", "rim", "rim.rehber", "admin2", "support-team", "qa.tester"):
            with self.subTest(value=value), self.assertRaises(UsernameChangeError) as ctx:
                validate_username(value)
            self.assertEqual(ctx.exception.code, "reserved")
        for value in ("rimma.aliyeva", "administrasiya", "rootkit.ali"):
            with self.subTest(value=value):
                validate_username(value)
        self._assert_rejected(self._post("Admin"), "ayrılıb")

    def test_cooldown(self):
        profile = self.user.profile
        profile.username_changed_at = timezone.now() - timedelta(days=5)
        profile.save(update_fields=["username_changed_at"])

        self._assert_rejected(self._post("aysel.q"), "tarixindən sonra")
        page = self.client.get(EDIT_URL)
        self.assertContains(page, "tarixindən sonra")

        profile.username_changed_at = timezone.now() - timedelta(days=31)
        profile.save(update_fields=["username_changed_at"])
        self._post("aysel.q")
        self.assertEqual(self._username(), "aysel.q")

    def test_second_change_is_blocked_by_default_cooldown(self):
        self._post("aysel.one")
        self.assertEqual(self._username(), "aysel.one")
        self._assert_rejected_from("aysel.one", self._post("aysel.two"))

    def _assert_rejected_from(self, expected, response):
        self.assertRedirects(response, EDIT_URL, fetch_redirect_response=False)
        self.assertEqual(self._username(), expected)

    def test_rate_limit_blocks_even_correct_password(self):
        for _ in range(10):
            with self.assertRaises(UsernameChangeError) as ctx:
                change_own_username(user=self.user, new_username="aysel.q", password="yanlis")
            self.assertEqual(ctx.exception.code, "wrong_password")
        with self.assertRaises(UsernameChangeError) as ctx:
            change_own_username(user=self.user, new_username="aysel.q", password=PASSWORD)
        self.assertEqual(ctx.exception.code, "rate_limited")
        self.assertEqual(self._username(), "aysel.quliyeva")

    def test_view_as_blocks_the_form(self):
        self.assertIn("change-username", ViewAsMiddleware.BLOCKED_PROFILE_FORMS)


@override_settings(RUNTIME_SETTINGS_ENABLED=True)
class UsernameChangeRuntimeSettingsTest(_Base):
    def _set(self, key, value):
        apps.get_model("accounts", "RuntimeSetting").objects.update_or_create(key=key, defaults={"value": value})
        runtime_settings.invalidate()

    def test_keys_are_registered_in_existing_profile_group(self):
        enabled = runtime_settings.SPECS["profile.username_change_enabled"]
        cooldown = runtime_settings.SPECS["profile.username_change_cooldown_days"]
        self.assertEqual((enabled.group, enabled.kind), ("profile", "bool"))
        self.assertEqual((cooldown.group, cooldown.kind, cooldown.min, cooldown.max), ("profile", "int", 0, 365))
        self.assertEqual([code for code, _label in runtime_settings.GROUPS].count("profile"), 1)
        self.assertTrue(username_change.change_enabled())
        self.assertEqual(username_change.cooldown_days(), 30)

    def test_toggle_off_hides_card_and_rejects_post(self):
        self._set("profile.username_change_enabled", False)

        page = self.client.get(EDIT_URL)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'id="usernameChangeCard"')
        response = self._post("aysel.q")
        self.assertEqual(self._username(), "aysel.quliyeva")
        self.assertTrue(any("mümkün deyil" in text for text in self._messages(response)))

    def test_cooldown_setting_zero_allows_immediate_change(self):
        self._set("profile.username_change_cooldown_days", 0)
        profile = self.user.profile
        profile.username_changed_at = timezone.now() - timedelta(minutes=1)
        profile.save(update_fields=["username_changed_at"])

        self._post("aysel.q")
        self.assertEqual(self._username(), "aysel.q")

    def test_cooldown_setting_is_used(self):
        self._set("profile.username_change_cooldown_days", 3)
        profile = self.user.profile
        profile.username_changed_at = timezone.now() - timedelta(days=4)
        profile.save(update_fields=["username_changed_at"])

        self._post("aysel.q")
        self.assertEqual(self._username(), "aysel.q")
