"""Sahib 2026-10-23: semestr başlanğıcında giriş / OTP limitləri maksimuma — heç kim bloklanmasın.

Miqrasiyanın yazdığı hər dəyər ``runtime_settings.coerce``-dan keçməlidir: keçməsə ``get`` səssizcə defolta
(dar limitə) qayıdardı və «maks» heç vaxt işləməzdi. İlk giriş səhifəsində «Spam»a baxın xəbərdarlığı görünür.
"""

from __future__ import annotations

import importlib

from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile
from core import runtime_settings

MIGRATION = importlib.import_module("apps.accounts.migrations.0035_runtime_limits_semester_start_2026_10_23")


class SemesterStartLimitValuesTest(SimpleTestCase):
    def test_every_value_is_accepted_by_its_spec(self):
        for key, value in MIGRATION.SEMESTER_START_MAXIMUMS.items():
            spec = runtime_settings.SPECS[key]
            self.assertIsNotNone(runtime_settings.coerce(spec, value), key)

    def test_values_are_the_spec_maximums(self):
        for key, value in MIGRATION.SEMESTER_START_MAXIMUMS.items():
            spec = runtime_settings.SPECS[key]
            if spec.kind == "rate":
                count, window = str(value).split("/")
                self.assertEqual((int(count), window), (spec.max, "1m"), key)
            elif key == "otp.resend_cooldown_seconds":
                self.assertEqual(value, spec.min, key)  # ən qısa fasilə = ən yumşaq
            else:
                self.assertEqual(value, spec.max, key)


class FirstLoginSpamNoteTest(TestCase):
    def test_spam_note_is_visible_on_the_email_step(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user("spam.note", "spam.note@example.com", "Initial-Pass-1")
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.password_change_required = True
        profile.email_verified = False
        profile.save(update_fields=["password_change_required", "email_verified", "updated_at"])
        client = Client()
        client.force_login(user)
        html = client.get(reverse("accounts:set_initial_password")).content.decode()
        self.assertIn('class="auth-spam-note"', html)
        self.assertIn("«Spam»", html)
