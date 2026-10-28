"""Tələbə bal məlumatı və nəticə kartında eyni sakit izah görünür."""

from django.template.loader import render_to_string
from django.test import SimpleTestCase


class ResultReconciliationNoticeTest(SimpleTestCase):
    def test_dashboard_notice_does_not_depend_on_password_reset(self):
        context = {
            "allowed_sections": ["dashboard"],
            "active_section": "dashboard",
            "role_capabilities": {"is_student": True},
            "dashboard_section": {},
            "grades_notice": False,
        }
        html = render_to_string("accounts/profile/sections/_dashboard.html", context)
        self.assertIn("result-reconciliation-notice", html)
        self.assertIn("İmtahan Mərkəzi", html)
        context["role_capabilities"]["is_student"] = False
        teacher_html = render_to_string("accounts/profile/sections/_dashboard.html", context)
        self.assertNotIn("result-reconciliation-notice", teacher_html)

    def test_every_result_card_keeps_notice_with_its_result(self):
        for category in ("exams", "academic", "labs"):
            with self.subTest(category=category):
                html = render_to_string(
                    "accounts/profile/sections/student_outcomes/_result_card.html",
                    {"item": {"title": "Fənn", "category": category, "status": "graded", "score": None}},
                )
                self.assertEqual(html.count("result-reconciliation-notice"), 1)
                self.assertIn("təsdiqlənən səhvlər düzəldilir", html)
                self.assertLess(html.index("result-reconciliation-notice"), html.index("</article>"))
