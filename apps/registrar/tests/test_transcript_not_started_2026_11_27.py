"""MR-000867 (2026-11-27): başlamamış semestrin fənnində «giriş balı» göstərilmir, davam edən fənnin hərfi yoxdur."""

import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils import timezone

from apps.registrar.transcript import _not_started


class NotStartedPeriodTest(SimpleTestCase):
    def test_future_period_is_not_started(self):
        today = timezone.localdate()
        self.assertTrue(_not_started(SimpleNamespace(start_date=today + datetime.timedelta(days=30))))
        self.assertFalse(_not_started(SimpleNamespace(start_date=today)))
        self.assertFalse(_not_started(SimpleNamespace(start_date=today - datetime.timedelta(days=30))))
        self.assertFalse(_not_started(SimpleNamespace(start_date=None)))
        self.assertFalse(_not_started(object()))

    def test_template_hides_entry_score_when_not_started(self):
        from pathlib import Path

        text = Path("apps/accounts/templates/accounts/profile/sections/_overall_academic.html").read_text()
        self.assertIn("{% if row.recognition or row.not_started %}—", text)
