"""Sillabus redaktoru — əl ilə semestr saatı (sahib 2026-09-25).

«Bir dəfə yazandan sonra edit etmək olmur, səhv yazılsa itdi getdi» + «dropdown olsun, əl ilə
yazılmasın»: rəsmi plan (tədris planı / dərs yükü) tapılmayanda saat SEÇİLİR (layihənin select
komponenti) və saxlanandan sonra da həmin formada dəyişdirilə bilir; rəsmi plan olanda forma yoxdur.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.syllabus import services
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org

User = get_user_model()


class ManualPlanHoursTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("syl-manual-hours")
        cls.teacher = User.objects.create_user("syl_mh_teacher", "syl_mh_teacher@x.test", "StrongPass123!")
        activate_member(
            cls.org,
            cls.teacher,
            "teacher",
            permissions=["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"],
            level=60,
        )
        stack = make_academic_stack(cls.org, code="SYLMH1")
        offering = make_offering(cls.org, stack, cls.teacher)
        actor = services.resolve_actor(cls.teacher, cls.org)
        cls.syllabus, cls.version = services.create_draft(
            organization=cls.org,
            subject=stack["subject"],
            period=stack["period"],
            actor=actor,
            offering=offering,
            program=stack["program"],
            chair_unit=stack["chair"],
            author=cls.teacher,
            plan_hours={},
        )

    def _html(self) -> str:
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(
            reverse("accounts:profile"), {"section": "syllabus-editor", "version": str(self.version.pk)}
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    @staticmethod
    def _form(html: str) -> str:
        start = html.find("data-syl-planhours")
        if start < 0:
            return ""
        return html[start : html.find("</form>", start)]

    @mock.patch("apps.registrar.public.plan_hours_for_offering", return_value={})
    def test_no_plan_shows_dropdowns_not_number_inputs(self, _plan):
        form = self._form(self._html())
        self.assertTrue(form, "plan tapılmayanda saat forması görünməlidir")
        self.assertNotIn('type="number"', form)
        self.assertEqual(form.count("data-bootstrap-select"), 3)
        self.assertIn('<option value="15"', form)
        self.assertIn('<option value="30"', form)

    @mock.patch("apps.registrar.public.plan_hours_for_offering", return_value={})
    def test_manual_hours_stay_editable_after_save(self, _plan):
        services.set_plan_hours(self.version, {"lecture": 10, "seminar": 5})
        form = self._form(self._html())
        self.assertTrue(form, "saxlanandan sonra da forma qalmalıdır (səhv seçim düzəldilə bilsin)")
        self.assertIn('<option value="10" selected', form)
        self.assertIn('<option value="5" selected', form)
        self.assertIn("Saatı yenilə", form)

    @mock.patch("apps.registrar.public.plan_hours_for_offering", return_value={"lecture": 30, "seminar": 15})
    def test_official_plan_hides_the_form(self, _plan):
        self.assertEqual(self._form(self._html()), "")
