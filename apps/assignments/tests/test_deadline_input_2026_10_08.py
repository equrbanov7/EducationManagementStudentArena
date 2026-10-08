"""Tapşırıq son tarixi — «gg.aa.iiii ss:dd» (24 saat), ISO da qəbul, Bakı vaxtı (sahib qərarı 2026-10-08)."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from apps.assignments.models import Assignment
from apps.assignments.tests import test_audit_2026_09_28_limits as base

BAKU = ZoneInfo("Asia/Baku")


class AssignmentDeadlineInputTests(base.AssignmentNumericLimitTests):
    # Baza sinfin testləri burada TƏKRAR işləməsin — yalnız fixture/köməkçilər götürülür.
    test_non_numeric_values_on_create_return_400 = None
    test_valid_and_default_values_on_create = None
    test_non_numeric_value_on_edit_returns_400_and_keeps_row = None

    def _local(self, value):
        return value.astimezone(BAKU).replace(tzinfo=None)

    def test_day_first_values_are_stored_in_baku_time(self):
        response = self._create(title="Gün-əvvəl", start_date="06.10.2026 09:30", deadline="10/10/2026 18:05")
        self.assertTrue(response.json()["success"], response.content[:300])
        created = Assignment.objects.get(id=response.json()["assignment_id"])
        self.assertEqual(self._local(created.start_date), datetime(2026, 10, 6, 9, 30))
        self.assertEqual(self._local(created.deadline), datetime(2026, 10, 10, 18, 5))

    def test_iso_still_accepted(self):
        response = self._create(title="ISO")
        self.assertTrue(response.json()["success"], response.content[:300])

    def test_unreadable_value_is_a_clear_400_not_500(self):
        response = self._create(title="Səhv", deadline="06.10.2026")
        self.assertEqual(response.status_code, 400)
        self.assertIn("ss:dd", response.json()["error"])
        self.assertFalse(Assignment.objects.filter(title="Səhv").exists())
        url = reverse("assignments:edit_assignment", args=[self.assignment.id])
        response = self.client.post(
            url, {"title": "X", "start_date": "31.02.2026 10:00", "deadline": "2026-10-05T10:00"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Assignment.objects.get(pk=self.assignment.pk).title, "SA10")

    def test_modal_renders_locale_free_inputs(self):
        request = RequestFactory().get("/")
        request.user = SimpleNamespace(is_teacher_or_above=True, is_authenticated=True, pk=self.owner.pk)
        html = render_to_string(
            "assignments/partials/_assignment_modals.html", {"course": self.course, "request": request}
        )
        self.assertNotIn("datetime-local", html)
        self.assertEqual(html.count("data-ems-dt-input"), 4)
        self.assertIn('id="editAsnDeadline"', html)
        self.assertIn("js/ems_datetime.js", html)
