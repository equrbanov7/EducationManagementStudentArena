"""Sahib 2026-10-25: «Gələn bildirişlərin dilini düzəlt — hərəsi bir dildə göstərir».

Aktivləşdirən tələbənin interfeys dili (ru/tr/en/az) RİM işçisinin bildiriş siyahısının dilini müəyyən ETMƏMƏLİDİR:
siyahı oxuyanın cari dilində göstərilir (başlıq, mətn, «RİM mərkəzində aç» etiketi).
"""

from __future__ import annotations

from django.conf import settings
from django.test import Client
from django.urls import reverse
from django.utils import translation

from apps.accounts.forms.otp import mark_self_service_password_set

from .test_rim_activation_notify_2026_10_23 import RimActivationBase, _activate, _activation_notes


class ActivationNotificationLanguageTests(RimActivationBase):
    def _activate_in(self, user, lang):
        _activate(user, verified=False, initial=True)
        with translation.override(lang), self.captureOnCommitCallbacks(execute=True):
            mark_self_service_password_set(user)

    def _inbox(self, lang) -> str:
        client = Client()
        client.force_login(self.operator)
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = lang
        response = client.get(reverse("accounts:profile"), {"section": "notifications"})
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_inbox_shows_every_activation_in_reader_language(self):
        self._activate_in(self.student, "ru")
        self._activate_in(self.teacher, "tr")
        self._activate_in(self.clerk, "en")
        self.assertEqual(_activation_notes().count(), 3)

        az = self._inbox("az")
        self.assertGreaterEqual(az.count("Profilini aktivləşdirdi:"), 3)  # sətir başlığı + data-atribut + aria
        for foreign in ("Профиль активирован", "Profilini etkinleştirdi", "Profile activated"):
            self.assertNotIn(foreign, az)
        self.assertIn("Cəmi aktivləşdirən:", az)
        self.assertNotIn("Всего активировали", az)

        ru = self._inbox("ru")
        self.assertIn("Профиль активирован:", ru)
        self.assertNotIn("Profilini aktivləşdirdi:", ru)
        self.assertNotIn("Profilini etkinleştirdi:", ru)

    def test_stored_columns_are_canonical_not_trigger_language(self):
        self._activate_in(self.student, "ru")
        note = _activation_notes().get()
        self.assertIn("Aysel Quliyeva", note.title)
        self.assertTrue(note.title.startswith("Profilini aktivləşdirdi:"))
        self.assertIn("Cəmi aktivləşdirən:", note.message)
        self.assertEqual(set(note.metadata["i18n"]), {"title", "message", "link_label"})
