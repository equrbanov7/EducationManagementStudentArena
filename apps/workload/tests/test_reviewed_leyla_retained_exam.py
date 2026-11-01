"""Load-only correction retains exact exam links, outcomes and all source cells."""

from unittest.mock import patch

from django.apps import apps
from django.test import TestCase

from apps.workload.services import reviewed_leyla_catalog_repair as repair
from apps.workload.services import reviewed_leyla_catalog_state as state
from apps.workload.services import reviewed_leyla_retained_exam as retained
from apps.workload.services.reviewed_leyla_catalog_graph import RepairError
from apps.workload.tests import test_reviewed_leyla_catalog as fixtures


class RetainedExamTests(TestCase):
    setUpTestData = classmethod(fixtures.ReviewedLeylaCatalogTests.setUpTestData.__func__)
    run_repair = fixtures.ReviewedLeylaCatalogTests.run_repair
    apply = fixtures.ReviewedLeylaCatalogTests.apply

    def setUp(self):
        fixtures.ReviewedLeylaCatalogTests.setUp(self)
        self.exam = apps.get_model("exams", "Exam").objects.create(
            id=92,
            organization=self.org,
            author=self.teacher,
            subject=self.rows[1].subject,
            title="Retained source exam",
            exam_type_extended="midterm",
        )
        Through = self.exam.journal_offerings.through
        for pk, offering in zip((64, 65), self.empty[1:]):
            Through.objects.create(pk=pk, exam=self.exam, courseoffering=offering)
        student = apps.get_model("registrar", "Enrollment").objects.filter(offering=self.filled[1]).first().student
        self.attempt = apps.get_model("exams", "ExamAttempt").objects.create(
            exam=self.exam,
            user=student,
            status="submitted",
            correct_count=0,
            wrong_count=20,
        )
        question = apps.get_model("exams", "ExamQuestion").objects.create(exam=self.exam, text="Retained question")
        self.answer = apps.get_model("exams", "ExamAnswer").objects.create(
            attempt=self.attempt,
            question=question,
            is_correct=False,
        )
        pin = dict(
            exam_id=92,
            organization_id=str(self.org.pk),
            author_id=self.teacher.pk,
            subject_id=str(self.rows[1].subject_id),
            links={64: str(self.empty[1].pk), 65: str(self.empty[2].pk)},
            pairs={str(a.pk): str(b.pk) for a, b in zip(self.empty[1:], self.filled[1:])},
        )
        self.patches.enter_context(patch.object(retained, "PIN", pin))

    def test_retained_exact_exam_graph_apply_repeat_and_undo_are_load_only(self):
        before = state.snapshot(self.org)
        for label, count in {
            "exams.Exam": 1,
            "exams.ExamAttempt": 1,
            "exams.ExamAnswer": 1,
            "exams.Exam_journal_offerings": 2,
            "exams.ExamQuestion": 1,
        }.items():
            self.assertEqual(before["protected"][label]["count"], count)
        result = self.apply()
        after = state.snapshot(self.org)
        self.assertEqual(repair._protected(before), repair._protected(after))
        self.assertEqual(self.run_repair(apply=True)["status"], "already_applied")
        self.attempt.refresh_from_db()
        self.answer.refresh_from_db()
        self.exam.refresh_from_db()
        self.assertEqual((self.attempt.correct_count, self.attempt.wrong_count, self.answer.is_correct), (0, 20, False))
        self.assertEqual(set(self.exam.journal_offerings.values_list("pk", flat=True)), {o.pk for o in self.empty[1:]})
        self.assertEqual(self.exam.subject_id, self.rows[1].subject_id)
        pending = self.run_repair(undo=result["receipt"])
        self.run_repair(undo=result["receipt"], apply=True, expected_baseline=pending["baseline"])
        self.assertEqual(repair._protected(before), repair._protected(state.snapshot(self.org)))

    def test_changed_exam_outcome_after_apply_blocks_undo(self):
        result = self.apply()
        apps.get_model("exams", "ExamAttempt").objects.filter(pk=self.attempt.pk).update(correct_count=1)
        with self.assertRaisesRegex(RepairError, "undo_state_changed"):
            self.run_repair(undo=result["receipt"])

    def test_any_extra_named_exam_reference_still_blocks(self):
        other = apps.get_model("exams", "Exam").objects.create(
            organization=self.org,
            author=self.teacher,
            title="Unreviewed extra",
        )
        other.journal_offerings.add(self.empty[1])
        with self.assertRaisesRegex(RepairError, "named_reference"):
            self.run_repair()

    def test_changed_source_exam_identity_is_rejected(self):
        apps.get_model("exams", "Exam").objects.filter(pk=self.exam.pk).update(subject=self.old_subjects[1])
        with self.assertRaisesRegex(RepairError, "retained_exam_identity"):
            self.run_repair()

    def test_real_attempt_outside_unique_canonical_student_set_is_rejected(self):
        apps.get_model("exams", "ExamAttempt").objects.create(exam=self.exam, user=self.actor, status="submitted")
        with self.assertRaisesRegex(RepairError, "attempt_student_unmatched"):
            self.run_repair()
