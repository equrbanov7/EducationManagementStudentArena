"""Alman dili (``de``) tam dəstəklənən interfeys dilidir — 2026-10-13 (gecə).

Sahib: «yeni dil əlavəsi etsin alman dili. select option-da görünsün. başqa hər yerdə də
işləsin, tərcümədə o da olsun.» Bu test həmin üç tələbi qoruyur:

1. Dil siyahısı/seçicilər — giriş səhifəsinin select-i «Deutsch» göstərir, ümumi dil
   seçicisində «DE» variantı var.
2. Dəyişmə işləyir — ``/i18n/setlang/`` ilə ``de`` seçilir, səhifə almanca render olunur,
   geri ``az``-a qayıtmaq da işləyir.
3. Kataloq — ``locale/de`` kataloqları var, kompilyasiya olunub, i18n qapısı «de»-ni də
   yoxlayır, JS kataloqu ``de`` üçün verilir.
"""

import os

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation
from django.utils.translation import pgettext

BASE = settings.BASE_DIR


def _catalog(lang, ctx, msgid):
    with translation.override(lang):
        return pgettext(ctx, msgid)


class GermanLanguageSettingsTest(TestCase):
    def test_de_is_in_languages_with_native_name(self):
        self.assertIn(("de", "Deutsch"), list(settings.LANGUAGES))

    def test_de_catalogs_exist_and_are_compiled(self):
        for domain in ("django", "djangojs"):
            for ext in ("po", "mo"):
                path = os.path.join(BASE, "locale", "de", "LC_MESSAGES", f"{domain}.{ext}")
                self.assertTrue(os.path.exists(path), path)

    def test_i18n_gate_checks_de_like_other_languages(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "check_i18n_catalogs", os.path.join(BASE, "scripts", "check_i18n_catalogs.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIn("de", module.LOCALES)

    def test_core_ui_strings_are_german(self):
        # Kataloqdan oxunur (hərfi mətn testə bişirilmir) — yalnız AZ-dan fərqli olmalıdır.
        for ctx, msgid in (
            ("accounts.login", "heading"),
            ("accounts.login", "title"),
            ("profile.sidebar", "group_general"),
            ("language", "name_de"),
        ):
            german = _catalog("de", ctx, msgid)
            self.assertTrue(german, (ctx, msgid))
            self.assertNotEqual(german, msgid, (ctx, msgid))
            self.assertNotEqual(german, _catalog("az", ctx, msgid), (ctx, msgid))
        self.assertEqual(_catalog("de", "language", "name_de"), "Deutsch")
        self.assertEqual(_catalog("az", "language", "name_de"), "Alman dili")


class GermanLanguageSwitchTest(TestCase):
    def test_login_select_offers_deutsch(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<option value="de"')
        self.assertContains(response, "Deutsch")

    def test_switch_to_german_and_back(self):
        login_url = reverse("accounts:login")
        response = self.client.post(reverse("set_language"), {"language": "de", "next": login_url})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.cookies[settings.LANGUAGE_COOKIE_NAME].value, "de")

        page = self.client.get(login_url)
        html = page.content.decode()
        self.assertIn('lang="de"', html)
        self.assertIn(_catalog("de", "accounts.login", "heading"), html)
        self.assertNotIn(_catalog("az", "accounts.login", "heading"), html)

        self.client.post(reverse("set_language"), {"language": "az", "next": login_url})
        self.assertEqual(self.client.cookies[settings.LANGUAGE_COOKIE_NAME].value, "az")
        html = self.client.get(login_url).content.decode()
        self.assertIn('lang="az"', html)
        self.assertIn(_catalog("az", "accounts.login", "heading"), html)

    def test_language_switcher_partial_has_de_option(self):
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        with translation.override("de"):
            html = render_to_string("partials/_language_switcher.html", {"request": request})
        self.assertIn('name="language" value="de"', html)
        self.assertIn("Deutsch", html)
        self.assertIn("DE", html)

    def test_javascript_catalog_is_served_for_de(self):
        from core.jsi18n import jsi18n_url

        with translation.override("de"):
            url = jsi18n_url()
        self.assertIn("l=de", url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class GermanLiveExamSessionLanguageTest(TestCase):
    def test_host_can_pick_german_for_player_pages(self):
        from apps.live_exam.i18n import session_language
        from apps.live_exam.session_settings import LANGUAGE_KEYS

        class _Session:
            host_settings = {"language": "de"}

        self.assertIn("de", LANGUAGE_KEYS)
        self.assertEqual(session_language(_Session()), "de")
