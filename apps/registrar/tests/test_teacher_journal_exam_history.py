"""Exam-only academic history remains discoverable without granting journal authority."""

from django.apps import apps
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.registrar import dashboard_data
from apps.registrar.page_contexts import journal_list_context
from apps.registrar.tests import test_teacher_journal_visibility as fixtures
from apps.workload.models import TeacherAssignment
from apps.workload.tests.factories import activate_member, make_structure


class TeacherJournalExamHistoryTests(TestCase):
    setUpTestData = classmethod(fixtures.TeacherJournalVisibilityTests.setUpTestData.__func__)
    request = fixtures.TeacherJournalVisibilityTests.request
    offering = fixtures.TeacherJournalVisibilityTests.offering
    assignment = fixtures.TeacherJournalVisibilityTests.assignment

    def board(self):
        return dashboard_data.teacher_offerings(
            organization=self.org, teacher=self.teacher, period=self.stack["period"]
        )

    def exam(self, offering, *, author=None, teacher=None):
        exam = apps.get_model("exams", "Exam").objects.create(
            organization=self.org,
            author=author or self.teacher,
            journal_teacher=teacher,
            title="Retained exact linked assessment",
            subject=offering.subject,
        )
        exam.journal_offerings.add(offering)
        return exam

    def attempt(self, exam, *, trial=False, status="submitted"):
        return apps.get_model("exams", "ExamAttempt").objects.create(
            exam=exam,
            user=self.other,
            status=status,
            is_trial=trial,
            attempt_number=exam.attempts.count() + 1,
        )

    def test_exact_owned_exam_attempt_without_any_lesson_keeps_history(self):
        offering = self.offering(instructor=self.teacher)
        exam = self.exam(offering)
        attempt = self.attempt(exam)
        row = self.board()["rows"][0]
        self.assertEqual(row["offering_id"], offering.pk)
        self.assertTrue(row["is_history"])
        self.assertFalse(row["own_history"])
        self.assertEqual(row["lessons_held"], 0)
        self.assertEqual(journal_list_context(self.teacher, self.request())["offerings"], [])
        history = journal_list_context(self.teacher, self.request(teaching="history"))["offerings"]
        self.assertEqual([o.pk for o in history], [offering.pk])
        self.assertTrue(history[0].journal_has_assessment_history)
        self.assertTrue(apps.get_model("exams", "ExamAttempt").objects.filter(pk=attempt.pk).exists())
        self.assertFalse(offering.lessons.exists())

    def test_real_journal_teacher_keeps_admin_authored_exam_activity(self):
        offering = self.offering(instructor=self.teacher)
        self.attempt(self.exam(offering, author=self.other, teacher=self.teacher))
        self.assertEqual([r["offering_id"] for r in self.board()["rows"]], [offering.pk])

    def test_trial_attempt_or_empty_exam_draft_does_not_resurrect_owner_only_extra(self):
        offering = self.offering(instructor=self.teacher)
        exam = self.exam(offering)
        self.assertEqual(self.board()["rows"], [])
        self.attempt(exam, trial=True)
        self.attempt(exam, status="draft")
        self.assertEqual(self.board()["rows"], [])

    def test_exam_authorship_never_adds_foreign_owned_journal_to_authorized_scope(self):
        offering = self.offering(instructor=self.other)
        self.attempt(self.exam(offering))
        self.assertEqual(self.board()["rows"], [])
        self.assertEqual(journal_list_context(self.teacher, self.request(teaching="history"))["offerings"], [])

    def test_another_teacher_exam_does_not_claim_current_owner_teaching_history(self):
        offering = self.offering(instructor=self.teacher)
        self.attempt(self.exam(offering, author=self.other, teacher=self.other))
        self.assertEqual(self.board()["rows"], [])

    def test_assigned_lab_with_zero_content_still_visible_in_lab_filter(self):
        offering = self.offering(instructor=self.teacher)
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.teacher, activity="lab", hours=15
        )
        rows = journal_list_context(self.teacher, self.request(kind="lab"))["offerings"]
        self.assertEqual([o.pk for o in rows], [offering.pk])
        self.assertFalse(self.board()["rows"][0]["is_history"])

    def test_department_reader_scope_is_not_expanded_by_exam_authorship(self):
        self.stack["period"].is_current = True
        self.stack["period"].save(update_fields=["is_current"])
        inside = self.offering(instructor=self.teacher)
        outside_stack = make_structure(self.org, code="EXAM-OUTSIDE")
        outside_stack["period"] = self.stack["period"]
        outside = self.offering(instructor=self.teacher, stack=outside_stack)
        self.attempt(self.exam(outside, author=self.other, teacher=self.other))
        activate_member(
            self.org,
            self.other,
            "scoped-journal-reader",
            permissions=["journal.view"],
            scope_unit=self.stack["faculty"],
            scope_type="unit",
        )
        context = journal_list_context(self.other, self.request(self.other))
        self.assertTrue(context["journal_is_broad"])
        self.assertEqual([o.pk for o in context["offerings"]], [inside.pk])

    def test_exam_attempt_volume_does_not_grow_dashboard_query_count(self):
        offering = self.offering(instructor=self.teacher)
        exam = self.exam(offering)
        self.attempt(exam)
        self.board()
        with CaptureQueriesContext(connection) as one:
            self.board()
        for i in range(2, 8):
            apps.get_model("exams", "ExamAttempt").objects.create(
                exam=exam, user=self.other, status="submitted", attempt_number=i
            )
        with CaptureQueriesContext(connection) as many:
            self.board()
        self.assertEqual(len(one), len(many))
