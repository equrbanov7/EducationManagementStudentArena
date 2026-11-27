from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.labs.models import LabAnswer, LabAssignment, LabBlock, LabQuestion, LabSubmission
from apps.labs.tests.test_views import LabDetailFixtureMixin


class QuestionHistoryTests(LabDetailFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.block = LabBlock.objects.create(lab=self.lab, title="Test")
        self.questions = [
            LabQuestion.objects.create(block=self.block, question_number=n, question_text=f"Question {n}")
            for n in (1, 2, 3)
        ]
        self.lab.questions_per_student = 1
        self.lab.save(update_fields=["questions_per_student"])
        self.assignment = LabAssignment.get_or_create_for_student(self.lab, self.student)
        self.first = self.assignment.assigned_questions.get()
        self._login_as(self.teacher)

    def test_saving_unchanged_limit_does_not_redraw_or_write_the_lab(self):
        previous = self.lab.updated_at
        with patch("apps.labs.models.assignment.secure_random.sample") as draw:
            response = self.client.post(
                reverse("labs:update_questions_per_student", args=[self.lab.pk]), {"questions_per_student": "1"}
            )
            self.lab.refresh_from_db()
            LabAssignment.get_or_create_for_student(self.lab, self.student)
        self.assertEqual(response.status_code, 302)
        draw.assert_not_called()
        self.assertEqual(self.lab.updated_at, previous)
        self.assertEqual(self.assignment.assigned_questions.get(), self.first)

    def test_draft_survives_a_real_limit_change_and_subsequent_student_visit(self):
        answer = LabAnswer.objects.create(lab=self.lab, question=self.first, student=self.student, answer="in progress")
        self.client.post(reverse("labs:update_questions_per_student", args=[self.lab.pk]), {"questions_per_student": 2})
        self._login_as(self.student)
        response = self.client.get(reverse("labs:lab_detail", args=[self.lab.pk]))
        self.assertContains(response, "in progress")
        self.assertEqual(self.assignment.assigned_questions.get(), self.first)
        answer.refresh_from_db()
        self.assertEqual(answer.question_id, self.first.pk)
        self.lab.refresh_from_db()
        self.assertEqual(self.lab.questions_per_student, 2)

    def test_changed_limit_applies_to_unstarted_assignment(self):
        self.client.post(reverse("labs:update_questions_per_student", args=[self.lab.pk]), {"questions_per_student": 2})
        self.lab.refresh_from_db()
        LabAssignment.get_or_create_for_student(self.lab, self.student)
        self.assertEqual(self.assignment.assigned_questions.count(), 2)

    def test_deleting_question_or_block_preserves_graded_answer_and_score(self):
        submission = LabSubmission.objects.create(assignment=self.assignment, status="graded", score=7)
        answer = LabAnswer.objects.create(
            lab=self.lab,
            question=self.first,
            student=self.student,
            submission=submission,
            answer="graded answer",
            score=7,
            is_draft=False,
        )
        for name, pk in (("delete_question", self.first.pk), ("delete_block", self.block.pk)):
            with self.subTest(name=name):
                response = self.client.post(reverse("labs:" + name, args=[pk]))
                self.assertEqual(response.status_code, 409)
                self.assertFalse(response.json()["success"])
                self.assertTrue(response.json()["error"])
        answer.refresh_from_db()
        submission.refresh_from_db()
        self.assertEqual((answer.question_id, answer.answer, answer.score), (self.first.pk, "graded answer", 7))
        self.assertEqual((submission.answers.count(), submission.score), (1, 7))
        self.assertEqual(self.block.questions.count(), 3)

    def test_can_still_delete_unused_block_and_question_but_draft_is_protected(self):
        LabAnswer.objects.create(lab=self.lab, question=self.first, student=self.student, answer="draft")
        used = self.client.post(reverse("labs:delete_question", args=[self.first.pk]))
        self.assertEqual(used.status_code, 409)
        unused = self.block.questions.exclude(pk=self.first.pk).first()
        self.assertTrue(self.client.post(reverse("labs:delete_question", args=[unused.pk])).json()["success"])
        other = LabBlock.objects.create(lab=self.lab, title="Extra")
        LabQuestion.objects.create(block=other, question_number=1, question_text="Other")
        self.assertTrue(self.client.post(reverse("labs:delete_block", args=[other.pk])).json()["success"])
        self.assertFalse(LabBlock.objects.filter(pk=other.pk).exists())
