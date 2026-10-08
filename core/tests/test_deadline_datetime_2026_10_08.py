"""Son tarix formaları — «gg.aa.iiii ss:dd» (24 saat), ISO da qəbul (sahib qərarı 2026-10-08).

Tapşırıq/laboratoriya/layihə/fənn qovluğu/elan son tarixləri native ``datetime-local`` idi
(brauzer dilinə tabe). Ortaq qatlar: ``core.helpers.parse_form_datetime``,
``DayFirstDateTimeField(allow_iso_date_only=...)`` və ``{% ems_datetime_input %}`` teqi.
"""

import datetime
from zoneinfo import ZoneInfo

from django import forms
from django.core.exceptions import ValidationError
from django.template import Context, Template
from django.test import SimpleTestCase, override_settings
from django.utils import translation

from core.datetime_input import DayFirstDateTimeField
from core.helpers import parse_form_datetime

BAKU = ZoneInfo("Asia/Baku")


@override_settings(USE_TZ=True, TIME_ZONE="Asia/Baku")
class ParseFormDatetimeTests(SimpleTestCase):
    def test_day_first_and_iso_become_baku_aware(self):
        for raw in ("06.10.2026 09:30", "06/10/2026 9:30", "2026-10-06T09:30", "2026-10-06 09:30:00"):
            with self.subTest(raw=raw):
                value = parse_form_datetime(raw)
                self.assertEqual(value.utcoffset(), datetime.timedelta(hours=4))
                self.assertEqual(value.astimezone(BAKU).replace(tzinfo=None), datetime.datetime(2026, 10, 6, 9, 30))

    def test_empty_and_aware_passthrough(self):
        self.assertIsNone(parse_form_datetime(""))
        self.assertIsNone(parse_form_datetime("   "))
        self.assertIsNone(parse_form_datetime(None))
        aware = datetime.datetime(2026, 10, 6, 5, 30, tzinfo=datetime.timezone.utc)
        self.assertEqual(parse_form_datetime(aware), aware)

    def test_iso_date_only_stays_valid_for_api_clients(self):
        value = parse_form_datetime("2026-10-06")
        self.assertEqual(value.astimezone(BAKU).replace(tzinfo=None), datetime.datetime(2026, 10, 6, 0, 0))

    def test_unreadable_value_raises_clear_message(self):
        with translation.override("az"):
            for raw, needle in (("06.10.2026", "ss:dd"), ("31.02.2026 10:00", "Belə tarix yoxdur"), ("sabah", "gg.aa")):
                with self.subTest(raw=raw):
                    with self.assertRaises(ValidationError) as ctx:
                        parse_form_datetime(raw)
                    self.assertIn(needle, ctx.exception.messages[0])


class _AnnForm(forms.Form):
    when = DayFirstDateTimeField(required=False, allow_iso_date_only=True)


class AllowIsoDateOnlyTests(SimpleTestCase):
    def test_iso_date_only_allowed_but_day_first_needs_time(self):
        self.assertTrue(_AnnForm({"when": "2026-10-06"}).is_valid())
        self.assertFalse(_AnnForm({"when": "06.10.2026"}).is_valid())
        self.assertTrue(_AnnForm({"when": "06.10.2026 10:00"}).is_valid())
        self.assertTrue(_AnnForm({"when": ""}).is_valid())


@override_settings(USE_TZ=True, TIME_ZONE="Asia/Baku")
class DatetimeInputTagTests(SimpleTestCase):
    def _render(self, snippet, **ctx):
        return Template("{% load ems_ui %}" + snippet).render(Context(ctx))

    def test_iso_value_is_shown_day_first(self):
        html = self._render(
            '{% ems_datetime_input "deadline" value input_id="addAsnDeadline" required=True %}',
            value="2026-10-06T09:30",
        )
        self.assertIn('value="06.10.2026 09:30"', html)
        self.assertIn('id="addAsnDeadline"', html)
        self.assertIn('name="deadline"', html)
        self.assertIn("required", html)
        self.assertIn('type="text"', html)
        self.assertNotIn("datetime-local", html)
        self.assertIn("data-ems-dt-toggle", html)

    def test_aware_value_uses_baku_and_ems_input_class(self):
        aware = datetime.datetime(2026, 10, 6, 5, 30, tzinfo=datetime.timezone.utc)
        html = self._render(
            '{% ems_datetime_input "due_at" value input_id="sfDeadlineDue" css_class="ems-input" describedby="x-hint" %}',
            value=aware,
        )
        self.assertIn('value="06.10.2026 09:30"', html)
        self.assertIn("ems-input", html)
        self.assertNotIn("form-control", html)
        self.assertIn('aria-describedby="x-hint sfDeadlineDue_hint"', html)

    def test_empty_and_unreadable_values(self):
        self.assertNotIn("value=", self._render('{% ems_datetime_input "a" "" input_id="a1" %}').split("<button")[0])
        self.assertIn('value="sabah"', self._render('{% ems_datetime_input "a" "sabah" input_id="a1" %}'))
