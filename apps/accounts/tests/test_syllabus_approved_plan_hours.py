"""Approved redaktorda görünən plan saatı autosave-in istifadə etdiyi saatla eyni qalır."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.accounts.views.syllabus.plan_hours_source import ensure_plan_hours


class ApprovedPlanHoursTest(SimpleTestCase):
    def test_approved_author_get_does_not_replace_saved_plan_with_new_curriculum(self):
        context = {
            "version": SimpleNamespace(status="approved"),
            "view_state": "normal",
            "is_author": True,
            "plan_hours": {"lecture": 30, "seminar": 15},
        }
        write = Mock()
        with patch("apps.accounts.views.syllabus.plan_hours_source.official_plan_hours") as official:
            hours, manual = ensure_plan_hours(SimpleNamespace(), context, write=write)
        self.assertEqual(hours, context["plan_hours"])
        self.assertFalse(manual)
        write.assert_not_called()
        official.assert_not_called()
