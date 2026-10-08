"""Layihə başlama/son tarixi — «gg.aa.iiii ss:dd» (24 saat), ISO da qəbul (sahib qərarı 2026-10-08)."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse

from apps.projects.models import Project
from apps.projects.tests import test_course_tasks_fix_2026_09_28 as base

BAKU = ZoneInfo("Asia/Baku")


class ProjectDeadlineInputTests(base.ProjectCourseTasksFixTests):
    def _post_create(self, **extra):
        payload = {
            "title": "Gün-əvvəl",
            "start_date": "06.10.2026 09:30",
            "deadline": "10.10.2026 18:05",
            "status": "active",
        }
        payload.update(extra)
        return self.client.post(reverse("projects:create_project", args=[self.course.id]), payload)

    def test_day_first_values_are_stored_in_baku_time(self):
        response = self._post_create()
        self.assertTrue(response.json()["success"], response.content[:300])
        project = Project.objects.get(id=response.json()["project_id"])
        self.assertEqual(project.start_date.astimezone(BAKU).replace(tzinfo=None), datetime(2026, 10, 6, 9, 30))
        self.assertEqual(project.deadline.astimezone(BAKU).replace(tzinfo=None), datetime(2026, 10, 10, 18, 5))

    def test_unreadable_value_is_a_clear_400_not_500(self):
        response = self._post_create(title="Səhv", deadline="sabah")
        self.assertEqual(response.status_code, 400)
        self.assertIn("gg.aa.iiii", response.json()["error"])
        self.assertFalse(Project.objects.filter(title="Səhv").exists())

    def test_modal_renders_locale_free_inputs(self):
        request = RequestFactory().get("/")
        request.user = SimpleNamespace(is_teacher_or_above=True, is_authenticated=True, pk=self.owner.pk)
        html = render_to_string("projects/partials/_project_modals.html", {"course": self.course, "request": request})
        self.assertNotIn("datetime-local", html)
        self.assertEqual(html.count("data-ems-dt-input"), 4)
        self.assertIn('id="editDeadline"', html)


# Baza sinfin testləri burada TƏKRAR işləməsin — yalnız fixture götürülür.
for _name in [n for n in vars(base.ProjectCourseTasksFixTests) if n.startswith("test_")]:
    if _name not in vars(ProjectDeadlineInputTests):
        setattr(ProjectDeadlineInputTests, _name, None)
