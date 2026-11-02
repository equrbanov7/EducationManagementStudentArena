"""Regular subjects show absences in q/b (1 q/b = one 2-hour lesson), never as raw hours.

Student applications (2026-11): «1 qayıbım var, saytda 2 görünür», «4 qayıbım var, 8
görünür, limitə düşmüşəm», «limiti keçmədiyim halda keçdiyim yazılıb».  The admission
decision was right (official table: 1 q/b = 2 academic hours, barred above 25% of the
subject's hours), but student surfaces printed the HOUR total next to a limit that
``floatformat:0`` rounded UP (30 h → 7.5 h shown as «8»), so a barred student read
«8 / 8 saat» while the teacher's grid said «4 q/b, limit 3 q/b».
"""

import datetime
from decimal import Decimal

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import translation

from apps.accounts.tests import test_exam_score_entry_section as fixtures
from apps.registrar import dashboard_data, exam_eligibility, page_contexts
from apps.registrar.models import Lesson, LessonMark, StudentAcademicRecord
from core.rls import bypass_rls


class ResolveQbFieldsTests(SimpleTestCase):
    def test_one_missed_two_hour_lesson_is_one_qb(self):
        result = exam_eligibility.resolve(absence_hours=2, lesson_hours=30, limit_percent=25)
        self.assertEqual(result["absence_count"], 1)
        self.assertEqual(result["limit_count"], 3)
        self.assertFalse(result["barred"])

    def test_four_qb_on_thirty_hours_is_over_the_three_qb_limit(self):
        # 8 h > 7.5 h (25% of 30) — the decision stays hour-based and unchanged,
        # but the student now reads «4 / 3 q/b» instead of «8 / 8 saat».
        result = exam_eligibility.resolve(absence_hours=8, lesson_hours=30, limit_percent=25)
        self.assertTrue(result["barred"])
        self.assertEqual(result["absence_count"], 4)
        self.assertEqual(result["limit_count"], 3)
        self.assertGreater(result["absence_count"], result["limit_count"])

    def test_forty_five_hour_subject_limit_uses_forty_five(self):
        result = exam_eligibility.resolve(absence_hours=10, lesson_hours=45, limit_percent=25)
        self.assertEqual(result["allowed_hours"], Decimal("11.25"))
        self.assertEqual(result["limit_count"], 5)
        self.assertFalse(result["barred"])
        over = exam_eligibility.resolve(absence_hours=12, lesson_hours=45, limit_percent=25)
        self.assertTrue(over["barred"])
        self.assertEqual(over["absence_count"], 6)

    def test_qb_limit_matches_hour_rule_for_every_whole_qb(self):
        for hours in (10, 15, 30, 45, 60, 75, 90, 105, 120):
            for count in range(0, 20):
                result = exam_eligibility.resolve(absence_hours=count * 2, lesson_hours=hours, limit_percent=25)
                self.assertEqual(result["barred"], count > result["limit_count"], (hours, count))

    def test_unknown_hours_have_no_qb_limit(self):
        result = exam_eligibility.resolve(absence_hours=4, lesson_hours=0)
        self.assertEqual(result["absence_count"], 2)
        self.assertIsNone(result["limit_count"])


@override_settings(UNIVERSITY_MODE=True)
class RegularStudentSurfacesTests(TestCase):
    setUpTestData = classmethod(fixtures.ExamScoreEntrySectionTest.setUpTestData.__func__)

    def prepare(self, lesson_hours):
        self.period.academic_year = "2026/2027"
        self.period.start_date = "2026-09-01"
        self.period.end_date = "2099-01-31"
        self.period.save()
        self.offering.period = self.period
        self.offering.lesson_hours = lesson_hours
        self.offering.save(update_fields=["lesson_hours"])
        self.record = StudentAcademicRecord.objects.select_related("program").get(student=self.student)
        self.enrollment.offering = self.offering

    def absences(self, count):
        for index in range(count):
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=datetime.date(2026, 9, 1) + datetime.timedelta(days=index),
                kind="seminar",
                hours=2,
            )
            LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=self.enrollment, status="absent")
        type(self.enrollment).objects.filter(pk=self.enrollment.pk).update(absence_hours=count * 2)
        self.enrollment.refresh_from_db()
        self.enrollment.offering = self.offering

    def render_surfaces(self):
        from apps.accounts.views.profile._sections.dashboard_student import _attendance_row
        from apps.registrar.public import build_student_journal_context

        request = RequestFactory().get("/accounts/profile/", {"subject": str(self.enrollment.pk)})
        request.user = self.student
        context = build_student_journal_context(request, organization=self.org)
        journal = context["journal_student_section"]["detail"]["journal"]
        detail = render_to_string("registrar/partials/_journal_student_content.html", context, request=request)
        row = {
            "enrollment": self.enrollment,
            "subject": self.subject,
            "journal": journal,
            "eligibility": journal["eligibility"],
            "ui": {"status": "ok"},
        }
        card = render_to_string("accounts/profile/sections/_my_subjects_card.html", {"row": row}, request=request)
        dashboard = dashboard_data.student_subjects(organization=self.org, record=self.record, period=self.period)
        info = next(r for r in dashboard["rows"] if r["offering_id"] == self.offering.pk)
        return journal, detail, card, info, _attendance_row(info, self.period)

    def test_one_missed_lesson_shows_one_qb_everywhere(self):
        with bypass_rls(), translation.override("az"):
            self.prepare(30)
            self.absences(1)
            journal, detail, card, info, widget = self.render_surfaces()
            self.assertEqual(journal["eligibility"]["absence_count"], 1)
            self.assertIn('value="1" max="3"', detail)
            self.assertNotIn('value="2"', detail)
            self.assertIn('value="1" max="3"', card)
            self.assertEqual(info["eligibility"]["absence_count"], 1)
            self.assertEqual(widget["value"], "Q/b 1 / 3")
            stats = page_contexts._student_offering_stats(self.student, self.org, self.record, self.period)
            self.assertEqual(stats[self.offering.pk]["eligibility"]["absence_count"], 1)
            self.assertEqual(stats[self.offering.pk]["eligibility"]["limit_count"], 3)

    def test_four_qb_on_thirty_hours_reads_over_limit_not_eight_of_eight(self):
        with bypass_rls(), translation.override("az"):
            self.prepare(30)
            self.absences(4)
            journal, detail, card, info, widget = self.render_surfaces()
            self.assertTrue(journal["barred"])
            self.assertTrue(info["eligibility"]["barred"])
            self.assertIn('value="4" max="3"', card)
            self.assertNotIn('value="8"', card)
            self.assertEqual(widget["value"], "Q/b 4 / 3")

    def test_forty_five_hour_subject_limit_is_five_qb(self):
        with bypass_rls(), translation.override("az"):
            self.prepare(45)
            self.absences(4)
            journal, detail, card, info, widget = self.render_surfaces()
            self.assertFalse(journal["barred"])
            self.assertEqual(info["eligibility"]["allowed_hours"], Decimal("11.25"))
            self.assertIn('value="4" max="5"', card)
            self.assertEqual(widget["value"], "Q/b 4 / 5")
