"""Personal dashboard uses the same positive-load/real-history list projection."""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.accounts.views.profile._sections.dashboard_teacher import _offering_row
from apps.organizations.models import Membership
from apps.registrar import dashboard_data
from apps.registrar.journal_access import is_direct_editor
from apps.registrar.models import CourseOffering, Curriculum, Enrollment, LessonMark, StudentAcademicRecord
from apps.registrar.page_contexts import journal_list_context
from apps.registrar.tests import test_teacher_journal_visibility as fixtures
from apps.workload.tests.factories import make_structure

User = get_user_model()


class DashboardTeacherJournalVisibilityTests(TestCase):
    setUpTestData = classmethod(fixtures.TeacherJournalVisibilityTests.setUpTestData.__func__)
    request = fixtures.TeacherJournalVisibilityTests.request
    offering = fixtures.TeacherJournalVisibilityTests.offering
    lesson = fixtures.TeacherJournalVisibilityTests.lesson
    assignment = fixtures.TeacherJournalVisibilityTests.assignment

    def board(self, user=None):
        return dashboard_data.teacher_offerings(
            organization=self.org, teacher=user or self.teacher, period=self.stack["period"]
        )

    def enroll(self, offering):
        student = User.objects.create_user("dashboard-visible-student")
        Membership.objects.create(organization=self.org, user=student, role=self.org.roles.get(name="student"))
        return Enrollment.objects.create(organization=self.org, offering=offering, student=student)

    def test_owner_only_one_enrollment_no_content_hidden_without_data_or_access_changes(self):
        offering = self.offering(instructor=self.teacher)
        enrollment = self.enroll(offering)
        self.assertTrue(is_direct_editor(self.teacher, offering))
        self.assertEqual(self.board()["rows"], [])
        for params in ({}, {"teaching": "history"}):
            self.assertEqual(journal_list_context(self.teacher, self.request(**params))["offerings"], [])
        self.assertTrue(CourseOffering.objects.filter(pk=offering.pk, is_active=True).exists())
        self.assertTrue(Enrollment.objects.filter(pk=enrollment.pk, status="enrolled").exists())
        self.assertTrue(is_direct_editor(self.teacher, offering))

    def test_positive_current_assignment_keeps_empty_unrestored_journal(self):
        offering = self.offering(instructor=self.teacher)
        self.assignment()
        row = self.board()["rows"][0]
        self.assertEqual(row["offering_id"], offering.pk)
        self.assertFalse(row["is_history"])
        self.assertEqual((row["students"], row["lessons_held"]), (0, 0))
        self.assertEqual([o.pk for o in journal_list_context(self.teacher, self.request())["offerings"]], [offering.pk])

    def test_unassigned_authored_lesson_kept_with_history_label_and_readonly_link(self):
        offering = self.offering(instructor=self.other)
        self.lesson(offering, instructor=self.teacher, hours=2)
        row = self.board()["rows"][0]
        self.assertEqual(row["offering_id"], offering.pk)
        self.assertTrue(row["is_history"])
        self.assertTrue(row["own_history"])
        rendered = _offering_row(row)
        self.assertIn("Tarixçə: cari yük təyinatı yoxdur", rendered["meta"])
        self.assertTrue(rendered["url"].endswith("?own_history=1"))
        self.assertFalse(is_direct_editor(self.teacher, offering))

    def test_own_mark_author_keeps_real_history_even_when_another_teacher_taught(self):
        offering = self.offering(instructor=self.other)
        enrollment = self.enroll(offering)
        lesson = self.lesson(offering, instructor=self.other)
        LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, score=0, entered_by=self.teacher
        )
        self.assertEqual([r["offering_id"] for r in self.board()["rows"]], [offering.pk])
        self.assertTrue(self.board()["rows"][0]["is_history"])

    def test_admin_all_journal_diagnostic_keeps_empty_owner_only_course(self):
        offering = self.offering(instructor=self.teacher)
        self.enroll(offering)
        admin = self.org.owner
        context = journal_list_context(admin, self.request(admin))
        self.assertTrue(context["journal_is_broad"])
        self.assertEqual([o.pk for o in context["offerings"]], [offering.pk])

    def test_impersonated_teacher_uses_effective_identity_not_real_admin(self):
        offering = self.offering(instructor=self.teacher)
        self.enroll(offering)
        request = self.request()
        request.real_user = self.org.owner
        request.is_view_as = True
        request.view_as_mode = "readonly"
        context = journal_list_context(request.user, request)
        self.assertFalse(context["journal_is_broad"])
        self.assertEqual(context["offerings"], [])
        self.assertEqual(self.board(request.user)["rows"], [])

    def test_student_journal_access_and_roster_stay_intact(self):
        offering = self.offering(instructor=self.teacher)
        enrollment = self.enroll(offering)
        curriculum = Curriculum.objects.create(
            organization=self.org, program=self.stack["program"], admission_year=2026
        )
        record = StudentAcademicRecord.objects.create(
            organization=self.org,
            student=enrollment.student,
            program=self.stack["program"],
            curriculum=curriculum,
            group=self.stack["group"],
            admission_year=2026,
        )
        before = dashboard_data.student_subjects(organization=self.org, record=record, period=self.stack["period"])[
            "rows"
        ]
        self.assertEqual([r["enrollment_id"] for r in before], [enrollment.pk])
        self.board()
        self.assertTrue(Enrollment.objects.filter(pk=enrollment.pk).exists())
        self.assertEqual(
            before,
            dashboard_data.student_subjects(organization=self.org, record=record, period=self.stack["period"])["rows"],
        )

    def test_query_count_constant_as_offering_count_grows(self):
        self.assignment()
        self.offering(instructor=self.teacher)
        self.board()
        with CaptureQueriesContext(connection) as one:
            self.board()
        for index in range(5):
            stack = make_structure(self.org, code=f"DTV{index}")
            stack["period"] = self.stack["period"]
            offering = self.offering(instructor=self.teacher, stack=stack)
            self.lesson(offering, instructor=self.teacher)
        self.board()
        with CaptureQueriesContext(connection) as many:
            self.board()
        self.assertEqual(len(one), len(many))
