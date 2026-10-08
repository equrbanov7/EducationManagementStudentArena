"""Elan vaxtları — «gg.aa.iiii ss:dd» (24 saat), köhnə ISO da qəbul (sahib qərarı 2026-10-08)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import translation

from apps.announcements.forms import AnnouncementForm

from .test_mandatory_manage_2026_10_07 import BASE
from .world import build_world, client_for

BAKU = ZoneInfo("Asia/Baku")


class AnnouncementDateFieldsTest(SimpleTestCase):
    def _form(self, **extra):
        return AnnouncementForm({**BASE, **extra})

    def test_day_first_and_iso_are_parsed_in_baku_time(self):
        form = self._form(publish_at="06.10.2030 09:30", expires_at="2030-10-20T18:00", deadline_at="2030-10-15")
        self.assertTrue(form.is_valid(), form.errors)
        data = form.cleaned_data
        self.assertEqual(data["publish_at"].astimezone(BAKU).replace(tzinfo=None), datetime(2030, 10, 6, 9, 30))
        self.assertEqual(data["expires_at"].astimezone(BAKU).replace(tzinfo=None), datetime(2030, 10, 20, 18, 0))
        self.assertEqual(data["deadline_at"].astimezone(BAKU).replace(tzinfo=None), datetime(2030, 10, 15, 0, 0))

    def test_unreadable_value_has_clear_error(self):
        with translation.override("az"):
            form = self._form(publish_at="06.10.2030")
            self.assertFalse(form.is_valid())
            self.assertIn("ss:dd", form.errors["publish_at"][0])


class AnnouncementFormPageTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("anndt")

    def test_form_page_renders_locale_free_inputs(self):
        client = client_for(self.w["org"], self.w["owner"])
        html = client.get(reverse("announcements:manage_create")).content.decode()
        self.assertNotIn("datetime-local", html)
        self.assertEqual(html.count("data-ems-dt-input"), 3)
        self.assertIn('aria-describedby="annm-deadline-hint annm-deadline_hint"', html)
        self.assertIn("js/ems_datetime.js", html)
