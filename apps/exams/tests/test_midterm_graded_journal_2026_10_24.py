"""Yazılı / kodlaşdırma midtermi → jurnalın «Midterm» xanası, TAM yoxlanılandan sonra (sahib 2026-10-24).

Test midtermi 2026-10-21-dən avtomatik yazılırdı; indi yazılı və praktiki (kodlaşdırma) midterm də eyni körpü
ilə (şkala, rəsmi cəhd, idempotentlik, audit, sənədli düzəliş, gizli nəticə, bağlı jurnal qaydaları) yazılır —
müəllim yoxlamanı bitirəndə (``manual_grading``) və ya kodlaşdırmanın test keysləri balı verəndə. Qismən
yoxlanmış cəhd yazılmır. Bax ``apps/exams/services/midterm_journal_sync.py``.
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.exams.models import Exam, ExamAnswer, ExamAttempt, ExamQuestion
from apps.exams.services import lifecycle, midterm_journal_sync
from apps.exams.services.manual_grading import apply_manual_grading, grading_complete
from apps.exams.tests.test_exam_journal_link_2026_10_24 import _LinkSetup, _login
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _AUDIT_TYPE, _MidtermSetup
from core.rls import bypass_rls


class _GradedSetup(_MidtermSetup):
    def _graded_exam(self, *, exam_type="written", points=(5, 5), category="midterm", **fields):
        with bypass_rls():
            exam = Exam.objects.create(
                title=f"MT {exam_type}",
                author=self.teacher,
                organization=self.org,
                subject=self.subject,
                exam_type=exam_type,
                exam_type_extended=category,
                is_active=True,
                **fields,
            )
            questions = [
                ExamQuestion.objects.create(exam=exam, order=order, text=f"Q{order}", points=value)
                for order, value in enumerate(points, start=1)
            ]
        return exam, questions

    def _submit(self, exam, questions, *, texts=None, **attempt_fields):
        """Tələbə cavab yazıb təhvil verir (cəhdin bitməsi körpünü çağırır — yoxlanmayıb, yazılmır)."""
        texts = texts if texts is not None else ["cavab"] * len(questions)
        with bypass_rls():
            attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress", **attempt_fields)
            for question, text in zip(questions, texts):
                ExamAnswer.objects.create(attempt=attempt, question=question, text_answer=text)
            with self.captureOnCommitCallbacks(execute=True):
                attempt.mark_finished(status="submitted")
        return attempt

    def _grade(self, attempt, scores):
        payload = {f"score_{question_id}": str(score) for question_id, score in scores.items()}
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            apply_manual_grading(attempt_id=attempt.pk, grader=self.teacher, payload=payload)
        with bypass_rls():
            attempt.refresh_from_db()
        return attempt

    def _last_audit(self):
        with bypass_rls():
            return AuditLog.objects.filter(resource_type=_AUDIT_TYPE).order_by("-created_at").first()


class WrittenMidtermGradedSyncTests(_GradedSetup):
    def test_submission_alone_does_not_write(self):
        exam, questions = self._graded_exam()
        self._submit(exam, questions)
        self.assertIsNone(self._score_row())

    def test_partially_graded_attempt_is_not_written(self):
        exam, questions = self._graded_exam()
        attempt = self._grade(self._submit(exam, questions), {questions[0].id: 5})
        self.assertTrue(attempt.checked_by_teacher)
        self.assertEqual(attempt.teacher_score, 5)  # yalnız yoxlanmış sualın cəmi — rəsmi bal deyil
        self.assertFalse(grading_complete(attempt))
        self.assertIsNone(self._score_row())
        with bypass_rls():
            status, row = midterm_journal_sync.sync_midterm_attempt(attempt)
        self.assertEqual((status, row), (midterm_journal_sync.GRADING_PENDING, None))

    def test_fully_graded_attempt_is_written_scaled_to_30_by_the_grader(self):
        exam, questions = self._graded_exam()
        attempt = self._submit(exam, questions)
        self._grade(attempt, {questions[0].id: 5})
        self._grade(attempt, {questions[1].id: 2})  # 7 / 10 = 70% × 30 = 21
        row = self._score_row()
        self.assertEqual(row.score, Decimal("21"))
        self.assertEqual(row.exam_source["attempt_id"], attempt.pk)
        self.assertEqual(row.exam_source["percent"], "70")
        self.assertEqual(row.entered_by, self.teacher)  # aktor — yoxlayan müəllim, tələbə deyil
        self.assertEqual(self._audit_count(), 1)
        self.assertEqual(self._last_audit().changes[0]["note"], "imtahan mərkəzi · yoxlama")
        self.assertIsNone(self._final_grade())  # FinalGrade-ə toxunulmur

    def test_regrade_updates_the_cell_and_is_idempotent(self):
        exam, questions = self._graded_exam()
        attempt = self._grade(self._submit(exam, questions), {questions[0].id: 5, questions[1].id: 5})
        self.assertEqual(self._score_row().score, Decimal("30"))
        self._grade(attempt, {questions[1].id: 0})  # yenidən yoxlama (redaktə pəncərəsi daxilində)
        self.assertEqual(self._score_row().score, Decimal("15"))
        self.assertEqual(self._audit_count(), 2)
        self._grade(attempt, {questions[1].id: 0})  # eyni bal — heç nə dəyişmir
        self.assertEqual(self._audit_count(), 2)

    def test_blank_answer_counts_as_zero_without_explicit_grade(self):
        exam, questions = self._graded_exam()
        attempt = self._grade(self._submit(exam, questions, texts=["cavab", "  "]), {questions[0].id: 4})
        self.assertTrue(grading_complete(attempt))
        self.assertEqual(self._score_row().score, Decimal("12"))  # 4 / 10 × 30

    def test_hidden_results_wait_until_published(self):
        exam, questions = self._graded_exam(results_hidden_from_students=True)
        self._grade(self._submit(exam, questions), {questions[0].id: 5, questions[1].id: 5})
        self.assertIsNone(self._score_row())
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(lifecycle.set_results_hidden(exam, False, by_user=self.teacher))
        self.assertEqual(self._score_row().score, Decimal("30"))

    def test_expelled_written_midterm_writes_zero_without_grading(self):
        exam, questions = self._graded_exam()
        self._submit(exam, questions, supervision_status="removed")
        self.assertEqual(self._score_row().score, Decimal("0"))

    def test_written_final_still_goes_to_final_grade(self):
        exam, questions = self._graded_exam(category="final", points=(10,))
        self._grade(self._submit(exam, questions), {questions[0].id: 8})
        self.assertEqual(self._final_grade().exam_score, Decimal("40"))
        self.assertIsNone(self._score_row())


class CodingMidtermGradedSyncTests(_GradedSetup):
    def _auto_scored(self, exam, questions, *, score):
        """Kodlaşdırma təhvili: test keysləri balı verib (``coding._finalize_coding_submit`` kimi)."""
        with bypass_rls():
            attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress")
            for question in questions:
                ExamAnswer.objects.create(attempt=attempt, question=question, text_answer="print(1)")
            attempt.teacher_score = score
            attempt.checked_by_teacher = True
            with self.captureOnCommitCallbacks(execute=True):
                attempt.mark_finished(status="submitted", extra_update_fields=["teacher_score", "checked_by_teacher"])
        return attempt

    def test_auto_scored_coding_midterm_is_written_on_submit(self):
        exam, questions = self._graded_exam(exam_type="coding", points=(10,))
        self._auto_scored(exam, questions, score=6)
        self.assertEqual(self._score_row().score, Decimal("18"))  # 60% × 30
        self.assertEqual(self._last_audit().changes[0]["note"], "imtahan mərkəzi · avtomatik")

    def test_manually_graded_coding_midterm_waits_for_every_question(self):
        exam, questions = self._graded_exam(exam_type="coding")
        attempt = self._submit(exam, questions)  # icra söndürülüb — bal yoxdur
        self.assertIsNone(self._score_row())
        self._grade(attempt, {questions[0].id: 3})
        self.assertIsNone(self._score_row())
        self._grade(attempt, {questions[1].id: 5})  # 8 / 10 × 30 = 24
        self.assertEqual(self._score_row().score, Decimal("24"))
        self._grade(attempt, {questions[0].id: 5})  # yenidən yoxlama → 30
        self.assertEqual(self._score_row().score, Decimal("30"))


class BackfillIncludesGradedFormatsTests(_GradedSetup):
    def _run(self, *args):
        out = StringIO()
        call_command("sync_midterm_scores", *args, stdout=out)
        return out.getvalue()

    def test_backfill_writes_graded_written_and_counts_pending(self):
        exam, questions = self._graded_exam()
        with mock.patch.object(midterm_journal_sync, "sync_midterm_attempt", return_value=("x", None)):
            self._grade(self._submit(exam, questions), {questions[0].id: 5, questions[1].id: 5})
        self.assertIsNone(self._score_row())
        out = self._run("--org", self.org.slug)
        self.assertIn("DRY-RUN", out)
        self.assertIn("written 1", out)
        self.assertIn("rəsmi midterm cəhdi 1", out)
        self.assertIn("written 1", self._run("--org", self.org.slug, "--apply"))
        self.assertEqual(self._score_row().score, Decimal("30"))
        self.assertIn("unchanged 1", self._run("--org", self.org.slug, "--apply"))

    def test_backfill_skips_partially_graded_written(self):
        exam, questions = self._graded_exam()
        self._grade(self._submit(exam, questions), {questions[0].id: 5})
        out = self._run("--org", self.org.slug, "--exam", exam.slug, "--apply")
        self.assertIn("grading_pending 1", out)
        self.assertIsNone(self._score_row())


class GradingScreenNoticeTests(_GradedSetup):
    def _page(self, attempt):
        client = _login(self.teacher, self.org)
        response = client.get(reverse("exams:teacher_check_attempt", args=[attempt.exam.slug, attempt.pk]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_written_midterm_grading_page_shows_auto_journal_note(self):
        exam, questions = self._graded_exam()
        html = self._page(self._submit(exam, questions))
        self.assertIn('data-tca-midterm-journal-note="auto"', html)
        self.assertIn("Bal jurnala avtomatik yazılır", html)

    def test_hidden_results_variant_and_final_has_no_note(self):
        exam, questions = self._graded_exam(results_hidden_from_students=True)
        self.assertIn('data-tca-midterm-journal-note="hidden"', self._page(self._submit(exam, questions)))
        with bypass_rls():
            ExamAttempt.objects.filter(exam=exam).delete()
            Exam.objects.filter(pk=exam.pk).update(exam_type_extended="final")
        html = self._page(self._submit(exam, questions))
        self.assertNotIn("data-tca-midterm-journal-note", html)


class WizardNoticeTests(_GradedSetup, _LinkSetup):
    def _form_html(self, exam):
        with bypass_rls():
            Exam.objects.filter(pk=exam.pk).update(author=self.center)  # imtahan mərkəzi — midterm/final sahibi
        client = _login(self.center, self.org)
        response = client.get(
            reverse("exams:edit_exam", kwargs={"slug": exam.slug}) + "?modal=1", HTTP_X_REQUESTED_WITH="XMLHttpRequest"
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_written_midterm_shows_after_grading_text(self):
        exam, _questions = self._graded_exam()
        html = self._form_html(exam)
        self.assertIn("data-ew-midterm-journal-note>", html)  # görünür (hidden yoxdur)
        self.assertIn('data-ew-journal-note-format="graded">', html)
        self.assertIn('data-ew-journal-note-format="test" hidden>', html)
        self.assertIn("nəticəsi yoxlanıldıqdan sonra seçilmiş fənnin qrup jurnallarına", html)

    def test_test_midterm_shows_on_finish_text_and_final_hides_note(self):
        exam, _questions = self._graded_exam(exam_type="test", points=(1,))
        html = self._form_html(exam)
        self.assertIn('data-ew-journal-note-format="test">', html)
        self.assertIn("tələbə imtahanı bitirən kimi", html)
        with bypass_rls():
            Exam.objects.filter(pk=exam.pk).update(exam_type_extended="final")
        self.assertIn("data-ew-midterm-journal-note hidden>", self._form_html(exam))
