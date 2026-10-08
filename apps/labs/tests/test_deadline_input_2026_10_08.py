"""Laboratoriya başlama/son tarixi — «gg.aa.iiii ss:dd» (24 saat), ISO da qəbul (sahib qərarı 2026-10-08)."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from apps.labs.models import Lab
from apps.labs.tests import test_course_tasks_fix_2026_09_28 as base

BAKU = ZoneInfo("Asia/Baku")


class LabDeadlineInputTests(base._LabFixture):
    def test_day_first_values_are_stored_in_baku_time(self):
        lab = self._create(title="Gün-əvvəl", start_datetime="06.10.2026 09:30", end_datetime="10.10.2026 18:05")
        self.assertEqual(lab.start_datetime.astimezone(BAKU).replace(tzinfo=None), datetime(2026, 10, 6, 9, 30))
        self.assertEqual(lab.end_datetime.astimezone(BAKU).replace(tzinfo=None), datetime(2026, 10, 10, 18, 5))

    def test_unreadable_value_is_a_clear_400(self):
        response = self.client.post(
            reverse("labs:create_lab", args=[self.course.id]),
            {"title": "Səhv", "start_datetime": "06.10.2026 25:00", "end_datetime": "2026-10-05T10:00"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("23:59", response.json()["error"])
        self.assertFalse(Lab.objects.filter(title="Səhv").exists())

    def test_edit_get_still_returns_local_iso_for_the_modal(self):
        lab = self._lab()
        data = self.client.get(reverse("labs:edit_lab", args=[lab.id])).json()["data"]
        self.assertRegex(data["start_datetime"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")  # JS «gg.aa.iiii ss:dd»-ə çevirir

    def test_modals_render_locale_free_inputs(self):
        request = RequestFactory().get("/")
        request.user = SimpleNamespace(is_teacher_or_above=True, is_authenticated=True, pk=self.owner.pk)
        html = "".join(
            render_to_string(name, {"course": self.course, "request": request})
            for name in (
                "labs/partials/lab_modals/_add_lab_modal.html",
                "labs/partials/lab_modals/_edit_lab_modal.html",
                "labs/partials/lab_modals/_scripts.html",
            )
        )
        self.assertNotIn("datetime-local", html)
        self.assertEqual(html.count("data-ems-dt-input"), 4)
        self.assertIn('id="editLabEnd"', html)
        self.assertIn("js/ems_datetime_picker.js", html)
