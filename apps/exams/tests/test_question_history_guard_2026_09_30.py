"""Təhlükəsizlik baxışı 2026-09-30 (H1/H2) — sual SİLMƏK cavab tarixçəsini məhv etməsin.

``ExamAnswer.question`` ``CASCADE``-dir: cavablı sualın silinməsi təqdim olunmuş
cəhdlərin cavablarını da silirdi; yazılan imtahandan bir neçə sualı silmək də
təsdiqsiz keçirdi. İndi hər silmədə istifadə yoxlaması və cavab yoxlaması var;
deaktivasiya (məlumat silmir) əvvəlki kimi işləyir.
"""

from apps.exams.models import ExamAnswer, ExamQuestion
from apps.exams.services.question_invariants import (
    MODE_DEACTIVATE,
    MODE_DELETE,
    ExamInUse,
    QuestionsHaveAnswers,
    remove_exam_questions,
)

from .test_question_removal_guard_2026_09_30 import _GuardFixture


class QuestionHistoryGuardTests(_GuardFixture):
    def test_delete_refused_when_submitted_attempt_has_answers(self):
        exam, questions = self._exam()
        attempt = self._attempt(exam, status="submitted")
        ExamAnswer.objects.create(attempt=attempt, question=questions[0])

        with self.assertRaises(QuestionsHaveAnswers):
            remove_exam_questions(exam, self._ids(questions), mode=MODE_DELETE, deactivate_exam=True)

        exam.refresh_from_db()
        self.assertTrue(exam.is_active)
        self.assertEqual(ExamQuestion.objects.filter(exam=exam).count(), 3)
        self.assertEqual(ExamAnswer.objects.filter(attempt=attempt).count(), 1)

    def test_delete_refused_for_subset_while_exam_is_being_written(self):
        exam, questions = self._exam()
        self._attempt(exam, status="in_progress")

        with self.assertRaises(ExamInUse):
            remove_exam_questions(exam, self._ids(questions[:2]), mode=MODE_DELETE)

        self.assertEqual(ExamQuestion.objects.filter(exam=exam).count(), 3)

    def test_deactivate_still_allowed_for_answered_questions(self):
        exam, questions = self._exam()
        attempt = self._attempt(exam, status="submitted")
        ExamAnswer.objects.create(attempt=attempt, question=questions[0])

        outcome = remove_exam_questions(exam, self._ids(questions[:1]), mode=MODE_DEACTIVATE)

        self.assertEqual(outcome.count, 1)
        questions[0].refresh_from_db()
        self.assertFalse(questions[0].is_active)
        self.assertEqual(ExamAnswer.objects.filter(attempt=attempt).count(), 1)

    def test_unanswered_questions_are_still_deleted(self):
        exam, questions = self._exam()

        outcome = remove_exam_questions(exam, self._ids(questions[:2]), mode=MODE_DELETE)

        self.assertEqual(outcome.count, 2)
        self.assertEqual(ExamQuestion.objects.filter(exam=exam).count(), 1)
