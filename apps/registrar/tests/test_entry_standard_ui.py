"""Müəllim və tələbə ekranlarında eyni dörd hissə görünür; tarixi cədvəl saxlanılır."""

from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.registrar import journal_extras
from apps.registrar.tests.entry_standard_fixture import EntryStandardFixture
from core.rls import bypass_rls


@override_settings(UNIVERSITY_MODE=True)
class EntryStandardUITest(EntryStandardFixture, TestCase):
    def test_teacher_new_and_legacy_headers(self):
        with bypass_rls():
            for key, midterm in (("M1", True), ("K1", False)):
                data = journal_extras.get_final_breakdown(self.fresh_offering(key))
                html = render_to_string("registrar/partials/_jd_final_breakdown.html", {"final_breakdown": data})
                self.assertEqual("Aktivlik" in html, midterm)
                self.assertEqual("Kollokvium orta balı" in html, not midterm)
                self.assertEqual("LAB. İŞİ" in html, not midterm)
                self.assertNotIn('style="', html)
                if midterm:
                    self.assertIn("9,33", html)
                    self.assertIn("8,5", html)
                    self.assertNotIn("Kollokvium 1", html)

    def test_student_subjects_results_and_journal_parts(self):
        user = self.records["esd_s0"].student
        client = self._client(user)
        base = reverse("accounts:profile")
        for section in ("my-subjects", "my-results", "my-journal"):
            params = {"section": section}
            if section == "my-journal":
                params.update(subject=str(self.enrollments["M1"]["esd_s0"].id), period=str(self.periods["new"].id))
            response = client.get(base, params)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "data-entry-standard")
            self.assertContains(response, "Aktivlik")
            self.assertContains(response, "9,33")
