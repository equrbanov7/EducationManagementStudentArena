"""Müəllim və tələbə ekranlarında eyni hissələr görünür; tarixi cədvəl saxlanılır.

Sahib 2026-10-10: yeni qaydada sərbəst iş sütunu/nişanı YOXDUR, Midterm «/30», seminar + lab olan fəndə
aktivlik «Seminar ortası · Lab ortası · Bal (5 + 5)» sütunları ilə; RİM-də köhnə qaydaya qayıdanda əvvəlki
görünüş (Sərbəst iş /10, Midterm /20, birgə orta) qayıdır."""

from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.registrar import journal_extras
from apps.registrar.tests.entry_standard_fixture import EntryStandardFixture
from core.rls import bypass_rls


def _render(data):
    return render_to_string("registrar/partials/_jd_final_breakdown.html", {"final_breakdown": data})


@override_settings(UNIVERSITY_MODE=True)
class EntryStandardUITest(EntryStandardFixture, TestCase):
    def test_teacher_new_and_legacy_headers(self):
        with bypass_rls():
            for key, midterm in (("M1", True), ("K1", False)):
                data = journal_extras.get_final_breakdown(self.fresh_offering(key))
                html = _render(data)
                self.assertEqual("Aktivlik" in html, midterm)
                self.assertEqual("Kollokvium orta balı" in html, not midterm)
                self.assertEqual("LAB. İŞİ" in html, not midterm)
                # Sərbəst iş yalnız keçmiş dövrdə (yeni qaydada RİM-də söndürülüb).
                self.assertEqual("SƏRBƏST İŞ" in html, not midterm)
                self.assertNotIn('style="', html)
                if midterm:
                    self.assertTrue(data["activity_split"])
                    self.assertFalse(data["selfwork_active"])
                    self.assertIn("/30", html)
                    self.assertIn("Seminar ortası", html)
                    self.assertIn("Lab ortası", html)
                    self.assertIn("9,33", html)  # davamiyyət
                    self.assertIn("8,33", html)  # seminar ortası (25 / 3)
                    self.assertIn("8,67", html)  # 4.17 + 4.50
                    self.assertIn("5 + 5", html)
                    self.assertNotIn("Kollokvium 1", html)

    def test_seminar_only_offering_keeps_single_activity_column(self):
        with bypass_rls():
            data = journal_extras.get_final_breakdown(self.fresh_offering("M2"))  # dərs/bal yoxdur
        self.assertFalse(data["activity_split"])
        html = _render(data)
        self.assertIn("Orta bal", html)
        self.assertNotIn("Seminar ortası", html)

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
            self.assertContains(response, "/30")
            body = response.content.decode()
            # Səhifədə bir neçə fənn ola bilər (sıra bazadan asılıdır) — M1-in bloku «8,67» olandır.
            blocks = [chunk.split("</div>", 1)[0] for chunk in body.split("data-entry-standard")[1:]]
            self.assertTrue(blocks)
            for badges in blocks:
                self.assertNotIn("Sərbəst iş", badges)
            self.assertTrue(any("8,67" in badges for badges in blocks), section)


@override_settings(UNIVERSITY_MODE=True, ACADEMIC_SELFWORK_ENABLED=True, ACADEMIC_ACTIVITY_SPLIT=False)
class EntryStandardOldRuleUITest(EntryStandardFixture, TestCase):
    """Geri dönüş: köhnə qaydada görünüş də əvvəlki kimidir."""

    def test_teacher_breakdown_shows_selfwork_and_midterm_20(self):
        with bypass_rls():
            data = journal_extras.get_final_breakdown(self.fresh_offering("M1"))
        self.assertTrue(data["selfwork_active"])
        self.assertFalse(data["activity_split"])
        html = _render(data)
        self.assertIn("SƏRBƏST İŞ", html)
        self.assertIn("/20", html)
        self.assertIn("8,5", html)  # birgə orta
        self.assertNotIn("Seminar ortası", html)

    def test_student_badges_show_selfwork(self):
        client = self._client(self.records["esd_s0"].student)
        response = client.get(
            reverse("accounts:profile"),
            {
                "section": "my-journal",
                "subject": str(self.enrollments["M1"]["esd_s0"].id),
                "period": str(self.periods["new"].id),
            },
        )
        self.assertEqual(response.status_code, 200)
        badges = response.content.decode().split("data-entry-standard", 1)[1].split("</div>", 1)[0]
        self.assertIn("Sərbəst iş", badges)
        self.assertIn("/20", badges)
