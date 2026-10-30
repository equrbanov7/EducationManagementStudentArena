"""Late independent work must survive undo of source-created course identities."""

from django.test import TestCase, override_settings

from apps.exams.models import Exam
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Program,
    StudentAcademicRecord,
    Subject,
)
from apps.surveys.models import SurveyCampaign, SurveyResponse, SurveyTemplate
from apps.workload.models import TeachingTaskRow
from apps.workload.services import reviewed_batch_state as state
from apps.workload.services.sbio235_state import RepairError

from . import test_reviewed_source_v2 as fixtures


@override_settings(RLS_TRANSACTION_SCOPED=True)
class ReviewedUndoReferenceTests(TestCase):
    setUpTestData = classmethod(fixtures.ReviewedV2Tests.setUpTestData.__func__)
    setUp = fixtures.ReviewedV2Tests.setUp
    tearDown = fixtures.ReviewedV2Tests.tearDown
    plan = fixtures.ReviewedV2Tests.plan
    execute = fixtures.ReviewedV2Tests.execute
    apply = fixtures.ReviewedV2Tests.apply
    new_subject = fixtures.ReviewedV2Tests.new_subject

    def created_course(self):
        entry = self.new_subject()
        plan = self.plan(entry)
        result = self.apply(plan)
        subject = Subject.objects.get(pk=entry["selected_subject_id"])
        return plan, result, subject, subject.offerings.get()

    def assert_undo_blocked(self, plan, result, subject, journal, code):
        before = state.snapshot(plan)
        rows = set(TeachingTaskRow.objects.values_list("pk", flat=True))
        with self.assertRaisesMessage(RepairError, code):
            self.execute(plan, undo=result["batch"], apply=True, expected_baseline=state.baseline(before))
        self.assertEqual(state.snapshot(plan), before)
        self.assertEqual(set(TeachingTaskRow.objects.values_list("pk", flat=True)), rows)
        self.assertTrue(Subject.objects.filter(pk=subject.pk).exists())
        self.assertTrue(CourseOffering.objects.filter(pk=journal.pk).exists())

    def survey(self, *, subject=None, offering=None):
        template = SurveyTemplate.objects.create(organization=self.org, name="Late course survey")
        campaign = SurveyCampaign.objects.create(organization=self.org, period=self.period, template=template)
        return SurveyResponse.objects.create(
            organization=self.org,
            campaign=campaign,
            scope="teacher" if offering else "general",
            subject=subject,
            offering=offering,
        )

    def test_late_exam_subject_reference_is_not_silently_set_null(self):
        plan, result, subject, journal = self.created_course()
        baseline = state.baseline(state.snapshot(plan))
        exam = Exam.objects.create(organization=self.org, author=self.admin, title="Late final", subject=subject)
        # Existing academic receipt alone did not notice this independent FK.
        self.assertEqual(state.baseline(state.snapshot(plan)), baseline)
        self.assert_undo_blocked(plan, result, subject, journal, "undo_created_subject_has_unreviewed_reference")
        exam.refresh_from_db()
        self.assertEqual(exam.subject_id, subject.pk)

    def test_late_hidden_survey_subject_reference_is_not_silently_set_null(self):
        plan, result, subject, journal = self.created_course()
        response = self.survey(subject=subject)
        self.assert_undo_blocked(plan, result, subject, journal, "undo_created_subject_has_unreviewed_reference")
        response.refresh_from_db()
        self.assertEqual(response.subject_id, subject.pk)

    def test_late_exam_journal_m2m_reference_is_preserved(self):
        plan, result, subject, journal = self.created_course()
        exam = Exam.objects.create(organization=self.org, author=self.admin, title="Linked final", subject=self.sa)
        exam.journal_offerings.add(journal)
        self.assert_undo_blocked(plan, result, subject, journal, "undo_created_journal_has_unreviewed_reference")
        self.assertTrue(exam.journal_offerings.filter(pk=journal.pk).exists())

    def test_late_hidden_survey_journal_reference_is_preserved(self):
        plan, result, subject, journal = self.created_course()
        response = self.survey(offering=journal)
        self.assert_undo_blocked(plan, result, subject, journal, "undo_created_journal_has_unreviewed_reference")
        response.refresh_from_db()
        self.assertEqual(response.offering_id, journal.pk)

    def test_protected_curriculum_reference_is_rejected_before_any_deletion(self):
        plan, result, subject, journal = self.created_course()
        program = Program.objects.create(organization=self.org, code="UNDO-LATE", name="Late independent plan")
        curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2026)
        row = CurriculumSubject.objects.create(
            organization=self.org,
            curriculum=curriculum,
            subject=subject,
            semester_number=1,
        )
        self.assert_undo_blocked(plan, result, subject, journal, "undo_created_subject_has_unreviewed_reference")
        self.assertTrue(CurriculumSubject.objects.filter(pk=row.pk, subject=subject).exists())

    def test_unrelated_exam_and_initial_batch_roster_do_not_block_valid_undo(self):
        program = Program.objects.create(
            organization=self.org, code="UNDO-ROSTER", name="Roster plan", specialty_unit=self.specialty
        )
        curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2023)
        StudentAcademicRecord.objects.create(
            organization=self.org,
            program=program,
            curriculum=curriculum,
            admission_year=2023,
            group=self.ga,
            student=self.a.enrollments.first().student,
        )
        plan, result, subject, journal = self.created_course()
        exam = Exam.objects.create(organization=self.org, author=self.admin, title="Unrelated", subject=self.sa)
        exam.journal_offerings.add(self.a)
        self.assertTrue(journal.enrollments.exists())
        current = state.baseline(state.snapshot(plan))
        self.execute(plan, undo=result["batch"], apply=True, expected_baseline=current)
        self.assertFalse(Subject.objects.filter(pk=subject.pk).exists())
        self.assertTrue(exam.journal_offerings.filter(pk=self.a.pk).exists())
        exam.refresh_from_db()
        self.assertEqual(exam.subject_id, self.sa.pk)
