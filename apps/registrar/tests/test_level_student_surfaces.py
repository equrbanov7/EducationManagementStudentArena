"""Real student/read/import surfaces honor level policy without changing raw schemes."""

import datetime
from decimal import Decimal
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import translation

from apps.accounts.tests import test_exam_score_entry_section as fixtures
from apps.registrar import (
    dashboard_data,
    exam_score_assessment,
    exam_score_entry,
    exam_score_import,
    guest_merge,
    page_contexts,
    student_display_policy,
)
from apps.registrar.models import AssessmentScheme, FinalGrade, Lesson, LessonMark, StudentAcademicRecord
from core.rls import bypass_rls

LEVEL_NAME = "Xarici dildə işgüzar və akademik kommunikasiya-1(elementary)"


class PreparedPolicyTests(SimpleTestCase):
    def enrollment(self, name=LEVEL_NAME):
        return SimpleNamespace(offering=SimpleNamespace(subject=SimpleNamespace(name=name)), absence_hours=22)

    def test_prepared_qb_count_resolves_without_database_reads(self):
        enrollment = self.enrollment()
        for count, barred in ((10, False), (11, True)):
            result = student_display_policy.eligibility(
                enrollment,
                absence_count=count,
                absence_hours=22,
                lesson_hours=300,
                allowed_hours=75,
                limit_percent=25,
                exempt=False,
                frozen=True,
            )
            self.assertEqual(result["barred"], barred)
            self.assertEqual(result["absence_count"], count)
            self.assertEqual(result["limit_count"], 10)

    def test_detail_uses_complete_summary_count_not_visible_mark_subset(self):
        prepared = {"barred": True, "absence_count": 11, "limit_count": 10}
        enrollment = self.enrollment()
        result = student_display_policy.detail_eligibility(
            enrollment,
            {"journal": {"eligibility": prepared}},
            SimpleNamespace(national_athlete_exemption=False),
            300,
            25,
        )
        self.assertIs(result, prepared)

    def test_warning_status_uses_qb_count_instead_of_double_hour_value(self):
        from apps.registrar.student_journal_context import warnings_for
        from apps.registrar.student_subjects_context import eligibility_status

        for count, expected in ((4, "ok"), (8, "near"), (10, "near"), (11, "barred")):
            result = {
                "limit_unit": "qb_count",
                "absence_count": count,
                "limit_count": 10,
                "absence_hours": count * 2,
                "allowed_hours": 10,
                "barred": count > 10,
                "frozen": False,
            }
            self.assertEqual(eligibility_status(result), expected)
            row = {
                "journal": {
                    "eligibility": result,
                    "barred": result["barred"],
                    "absence_hours": count * 2,
                    "allowed_absence": 10,
                }
            }
            self.assertEqual(bool(warnings_for([row])), expected != "ok")

    def test_regular_policy_stays_percent_based_and_caps_preserve_config(self):
        enrollment = self.enrollment("Programming")
        result = student_display_policy.eligibility(
            enrollment,
            absence_count=11,
            absence_hours=22,
            lesson_hours=300,
            limit_percent=25,
            exempt=False,
            frozen=False,
        )
        self.assertFalse(result["barred"])
        self.assertEqual(student_display_policy.entry_cap(enrollment.offering, SimpleNamespace(entry_score_max=40)), 40)
        self.assertEqual(student_display_policy.entry_cap(enrollment.offering, None), 50)
        self.assertEqual(student_display_policy.entry_cap(self.enrollment().offering, None), 30)


@override_settings(UNIVERSITY_MODE=True)
class LevelStudentSurfacesTests(TestCase):
    setUpTestData = classmethod(fixtures.ExamScoreEntrySectionTest.setUpTestData.__func__)

    def prepare(self, *, level=True):
        self.subject.name = LEVEL_NAME if level else "Programming"
        self.subject.save(update_fields=["name"])
        # Old 50 is intentionally retained in storage. Every read must normalize.
        AssessmentScheme.objects.update_or_create(
            organization=self.org, offering=self.offering, defaults={"entry_score_max": 50}
        )
        self.period.academic_year = "2026/2027"
        self.period.start_date = "2026-09-01"
        self.period.end_date = "2099-01-31"
        self.period.save()
        self.offering.subject = self.subject
        self.offering.period = self.period
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

    def test_dashboard_and_schedule_modal_show_30_and_bar_at_eleven_cells(self):
        with bypass_rls():
            self.prepare()
            self.absences(11)
            dashboard = dashboard_data.student_subjects(organization=self.org, record=self.record, period=self.period)
            row = next(r for r in dashboard["rows"] if r["offering_id"] == self.offering.pk)
            self.assertEqual(row["entry_max"], 30)
            self.assertTrue(row["eligibility"]["barred"])
            stats = page_contexts._student_offering_stats(self.student, self.org, self.record, self.period)
            self.assertEqual(stats[self.offering.pk]["entry_score_max"], 30)
            self.assertTrue(stats[self.offering.pk]["barred"])
            self.assertEqual(AssessmentScheme.objects.get(offering=self.offering).entry_score_max, 50)

    def test_ten_actual_cells_remain_allowed_with_stale_denormalized_hours(self):
        with bypass_rls():
            self.prepare()
            self.absences(10)
            type(self.enrollment).objects.filter(pk=self.enrollment.pk).update(absence_hours=999)
            dashboard = dashboard_data.student_subjects(organization=self.org, record=self.record, period=self.period)
            row = next(r for r in dashboard["rows"] if r["offering_id"] == self.offering.pk)
            self.assertFalse(row["eligibility"]["barred"])
            self.assertEqual(row["eligibility"]["absence_count"], 10)
            self.assertEqual(row["absence_hours"], Decimal(20))
            stats = page_contexts._student_offering_stats(self.student, self.org, self.record, self.period)
            self.assertFalse(stats[self.offering.pk]["barred"])
            self.assertEqual(stats[self.offering.pk]["absence_hours"], Decimal(20))

    def test_student_card_progress_and_dashboard_label_use_qb_units(self):
        from apps.accounts.views.profile._sections.dashboard_student import _attendance_row
        from apps.registrar.public import build_student_journal_context

        with bypass_rls(), translation.override("az"):
            self.prepare()
            self.absences(4)
            request = RequestFactory().get("/accounts/profile/", {"subject": str(self.enrollment.pk)})
            request.user = self.student
            context = build_student_journal_context(request, organization=self.org)
            section = context["journal_student_section"]
            html = render_to_string("registrar/partials/_journal_student_content.html", context, request=request)
            self.assertIn('value="4" max="10"', html)
            self.assertIn("Q/b)", html)
            self.assertNotIn('value="8" max="10"', html)
            row = {
                "enrollment": self.enrollment,
                "subject": self.subject,
                "journal": section["detail"]["journal"],
                "eligibility": section["detail"]["journal"]["eligibility"],
                "ui": {"status": "ok"},
            }
            card = render_to_string("accounts/profile/sections/_my_subjects_card.html", {"row": row}, request=request)
            self.assertIn('value="4" max="10"', card)
            self.assertIn("Q/b", card)
            dashboard = dashboard_data.student_subjects(organization=self.org, record=self.record, period=self.period)
            info = next(r for r in dashboard["rows"] if r["offering_id"] == self.offering.pk)
            widget = _attendance_row(info, self.period)
            self.assertEqual(widget["value"], "Q/b 4 / 10")
            self.assertEqual(widget["bar"]["value"], "4")

    def test_student_journal_detail_uses_level_cap_and_complete_summary_eligibility(self):
        from apps.registrar.public import build_student_journal_context

        with bypass_rls():
            self.prepare()
            self.absences(11)
            request = RequestFactory().get("/accounts/profile/", {"subject": str(self.enrollment.pk)})
            request.user = self.student
            section = build_student_journal_context(request, organization=self.org)["journal_student_section"]
            self.assertEqual(section["detail"]["entry_score_max"], 30)
            self.assertTrue(section["detail"]["dav_barred"])

    def test_predecessor_source_cap_and_scores_have_constant_batch_queries(self):
        with bypass_rls():
            self.prepare()
            for count in (1, 4):
                with self.assertNumQueries(6):
                    scores, caps = guest_merge._source_entry_scores([self.enrollment] * count, {})
                self.assertEqual(caps[self.offering.pk], 30)
                self.assertEqual(scores[self.enrollment.pk], Decimal(10))

    def test_final_import_accepts_70_and_rejects_71_then_bulk_write_keeps_70(self):
        with bypass_rls():
            self.prepare()
            roster = exam_score_entry.roster_for_offering(offering=self.offering)
            self.assertEqual(roster["exam_score_max"], 70)
            for value, status in (("70", exam_score_import.STATUS_NEW), ("71", exam_score_import.STATUS_ERROR)):
                plan = exam_score_import.build_plan(
                    roster=roster, rows=[{"_row": 2, "key": self.student.username, "score": value}]
                )
                self.assertEqual(plan[0]["status"], status)
                if value == "70":
                    valid = plan
            result = exam_score_import.apply_plan(offering=self.offering, plan=valid, by_user=self.center)
            self.assertEqual(result["written"], 1)
            self.assertEqual(FinalGrade.objects.get(enrollment=self.enrollment).exam_score, Decimal(70))

    def test_old_midterm_25_stays_raw_but_roster_and_new_writes_use_10(self):
        from apps.registrar import exam_score_midterm
        from apps.registrar.exam_score_period_lock import PeriodWritePolicy
        from apps.registrar.models import AssessmentComponent, ComponentScore

        with bypass_rls():
            self.prepare()
            component = AssessmentComponent.objects.create(
                organization=self.org, offering=self.offering, name="Midterm", kind="kollokvium", max_score=30
            )
            old = ComponentScore.objects.create(
                organization=self.org, component=component, enrollment=self.enrollment, score=25
            )
            roster = exam_score_midterm.roster_for_offering(offering=self.offering)
            self.assertEqual(roster["exam_score_max"], 10)
            result = exam_score_midterm.save_rows(
                offering=self.offering,
                rows=[{"enrollment_id": str(self.enrollment.pk), "score": "11"}],
                by_user=self.center,
                policy=PeriodWritePolicy(),
            )
            self.assertEqual(result["failed"], 1)
            old.refresh_from_db()
            self.assertEqual(old.score, Decimal(25))
            unchanged = exam_score_midterm.save_rows(
                offering=self.offering,
                rows=[{"enrollment_id": str(self.enrollment.pk), "score": "25"}],
                by_user=self.center,
                policy=PeriodWritePolicy(),
            )
            self.assertEqual(unchanged["failed"], 0)
            self.assertEqual(unchanged["written"], 0)
            from apps.registrar import interim_assessment, midterm_bridge

            interim = interim_assessment.spec_for_offering(self.offering)
            displayed = midterm_bridge.student_interim_rows(interim, [component], self.enrollment)
            self.assertEqual(displayed[0]["score"], Decimal(10))
            self.assertEqual(displayed[0]["component"].max_score, 10)
            dashboard = dashboard_data.student_subjects(organization=self.org, record=self.record, period=self.period)
            row = next(r for r in dashboard["rows"] if r["offering_id"] == self.offering.pk)
            self.assertEqual(row["interim"][0]["max"], 10)
            self.assertEqual(row["interim"][0]["score"], Decimal(10))
            old.refresh_from_db()
            self.assertEqual(old.score, Decimal(25))
            auto_status, _ = midterm_bridge.record_midterm_result(
                student=self.student,
                subject_id=self.subject.pk,
                organization=self.org,
                score_percent=80,
                attempt_id=1178,
                notify=False,
                by_user=self.center,
            )
            self.assertEqual(auto_status, midterm_bridge.OVERRIDDEN)
            old.refresh_from_db()
            self.assertEqual(old.score, Decimal(25))

    def test_automatic_midterm_uses_10_and_same_outcome_replay_preserves_old_raw_scale(self):
        from apps.registrar import midterm_bridge
        from apps.registrar.models import AssessmentComponent, ComponentScore
        from core.rls import journal_unlock

        with bypass_rls():
            self.prepare()
            component = AssessmentComponent.objects.create(
                organization=self.org, offering=self.offering, name="Midterm", kind="kollokvium", max_score=30
            )
            fields = {
                "student": self.student,
                "subject_id": self.subject.pk,
                "organization": self.org,
                "score_percent": Decimal("83.33"),
                "attempt_id": 1177,
                "notify": False,
                "by_user": self.center,
            }
            status, cell = midterm_bridge.record_midterm_result(**fields)
            self.assertEqual(status, midterm_bridge.WRITTEN)
            self.assertEqual(cell.score, Decimal(8))
            AssessmentComponent.objects.filter(pk=component.pk).update(max_score=30)
            with journal_unlock():
                ComponentScore.objects.filter(pk=cell.pk).update(score=25)
            status, repeated = midterm_bridge.record_midterm_result(**fields)
            self.assertEqual(status, midterm_bridge.UNCHANGED)
            repeated.refresh_from_db()
            self.assertEqual(repeated.score, Decimal(25))

    def test_regular_final_import_keeps_50_and_level_midterm_is_10(self):
        with bypass_rls():
            self.prepare(level=False)
            roster = exam_score_entry.roster_for_offering(offering=self.offering)
            self.assertEqual(roster["exam_score_max"], 50)
            self.assertEqual(exam_score_assessment.cap_for(self.offering, "midterm"), 30)
            plan = exam_score_import.build_plan(
                roster=roster, rows=[{"_row": 2, "key": self.student.username, "score": "70"}]
            )
            self.assertEqual(plan[0]["status"], exam_score_import.STATUS_ERROR)
            self.offering.subject.name = LEVEL_NAME
            self.assertEqual(exam_score_assessment.cap_for(self.offering, "midterm"), 10)
