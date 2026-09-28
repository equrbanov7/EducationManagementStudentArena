"""Audit 2026-09-28 (WP A2) — qiymətləndirmə bütövlüyü reqressiya testləri.

* EX28-02 (P1): müəllim YAZMAQDA olan tələbənin cəhdini yoxlaya bilirdi → qismən bal
  jurnala sinxronlaşır, 5 dəqiqədən sonra isə dondurulurdu;
* EXA-01 (P1) / EX28-06 (P2): köhnə cəhdin apellyasiyası / gecikmiş yoxlaması sonrakı
  (rəsmi) təkrar imtahanın jurnal balını əzirdi;
* EX28-03 (P2): çox-cəhdli imtahanda N-ci cəhdin cavab açarı dərhal açılırdı;
* EX28-09 (P3): coding ZIP-i org-dakı İSTƏNİLƏN müəllim yükləyə bilirdi.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import (
    CodingSubmission,
    Exam,
    ExamAnswer,
    ExamAttempt,
    ExamQuestion,
    StudentExamAttemptGrant,
)
from apps.exams.services.coding_definition import upsert_coding_question
from apps.exams.services.journal_sync import (
    SKIP_NOT_FINISHED,
    SKIP_SUPERSEDED_ATTEMPT,
    journal_sync_skips_total,
    sync_attempt_to_journal,
)
from apps.exams.services.manual_grading import (
    ManualGradingAttemptNotFinished,
    apply_attempt_grade,
    apply_manual_grading,
    apply_single_answer_grade,
)
from apps.exams.services.result_release import attempt_answer_key_hidden
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import (
    LOCMEM_CACHE,
    PASSWORD,
    _make_people,
    _make_quiz,
    _student_client,
)
from apps.exams.tests.test_journal_bridge import _JournalBridgeSetup
from apps.exams.tests.test_views import _assign_user_to_org
from apps.exams.views.teacher.results._helpers import _resolve_attempt_action_state
from core.rls import bypass_rls

User = get_user_model()


def _skips(reason):
    return journal_sync_skips_total.labels(reason=reason)._value.get()


class UnfinishedAttemptGradingServiceTests(_JournalBridgeSetup):
    """EX28-02 — servis qatı: bitməmiş cəhd qiymətləndirilmir və jurnala yazılmır."""

    def _open_written_attempt(self):
        exam, question = self._written_exam(points=10)
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress")
        answer = ExamAnswer.objects.create(attempt=attempt, question=question, text_answer="yarımçıq")
        return attempt, question, answer

    def test_manual_grading_refuses_in_progress_attempt(self):
        attempt, question, answer = self._open_written_attempt()

        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(ManualGradingAttemptNotFinished):
                apply_manual_grading(attempt_id=attempt.id, grader=self.teacher, payload={f"score_{question.id}": "3"})

        answer.refresh_from_db()
        attempt.refresh_from_db()
        self.assertIsNone(answer.teacher_score)
        self.assertFalse(attempt.checked_by_teacher)
        self.assertIsNone(attempt.teacher_checked_at, "5 dəqiqəlik pəncərə başlamamalıdır")
        self.assertIsNone(self._final_grade())

    def test_attempt_level_and_single_answer_grading_refuse_draft_attempt(self):
        attempt, _question, answer = self._open_written_attempt()
        ExamAttempt.objects.filter(pk=attempt.pk).update(status="draft")

        with bypass_rls():
            with self.assertRaises(ManualGradingAttemptNotFinished):
                apply_attempt_grade(attempt_id=attempt.id, score=5, feedback="", grader=self.teacher)
            with self.assertRaises(ManualGradingAttemptNotFinished):
                apply_single_answer_grade(answer_id=answer.id, score=5, grader=self.teacher)

        answer.refresh_from_db()
        self.assertIsNone(answer.teacher_score)

    def test_journal_sync_skips_unfinished_attempt(self):
        attempt, _question, _answer = self._open_written_attempt()
        attempt.teacher_score = 3  # köhnə yolla yazılmış qismən bal
        attempt.save(update_fields=["teacher_score"])
        before = _skips(SKIP_NOT_FINISHED)

        with bypass_rls():
            self.assertIsNone(sync_attempt_to_journal(attempt, actor=self.teacher))

        self.assertIsNone(self._final_grade())
        self.assertEqual(_skips(SKIP_NOT_FINISHED), before + 1)

    def test_finished_attempt_is_still_gradeable(self):
        attempt, question, _answer = self._open_written_attempt()
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            attempt.mark_finished(status="submitted")
            apply_manual_grading(attempt_id=attempt.id, grader=self.teacher, payload={f"score_{question.id}": "8"})

        self.assertEqual(self._final_grade().exam_score, Decimal("40"))


@override_settings(CACHES=LOCMEM_CACHE)
class UnfinishedAttemptTeacherViewTests(TestCase):
    """EX28-02 — UI: «Yoxla» yalnız bitmiş cəhdə; yoxlama URL-i açıq cəhdi baxışa yönləndirir."""

    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("a2ck")
        cls.exam = Exam.objects.create(
            title="A2 Written", author=cls.teacher, organization=cls.org, exam_type="written", is_active=True
        )
        cls.question = ExamQuestion.objects.create(exam=cls.exam, order=1, text="Esse", points=10)

    def setUp(self):
        # Cavab sətri YOXDUR — köhnə GET tələbənin açıq cəhdinə sual generasiya edirdi.
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
        self.client = _student_client("a2ck_teacher", self.org)
        self.check_url = reverse("exams:teacher_check_attempt", args=[self.exam.slug, self.attempt.id])
        self.view_url = reverse("exams:teacher_view_attempt", args=[self.exam.slug, self.attempt.id])

    def test_check_get_redirects_to_view_only_without_touching_the_attempt(self):
        response = self.client.get(self.check_url)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(self.view_url))
        self.assertFalse(self.attempt.answers.exists(), "GET tələbənin cəhdinə yazmamalıdır")

    def test_check_post_does_not_grade_open_attempt(self):
        ExamAnswer.objects.create(attempt=self.attempt, question=self.question, text_answer="yarımçıq")

        response = self.client.post(self.check_url, {f"score_{self.question.id}": "3"})

        self.assertEqual(response.status_code, 302)
        self.attempt.refresh_from_db()
        self.assertFalse(self.attempt.checked_by_teacher)
        self.assertIsNone(self.attempt.teacher_score)
        self.assertIsNone(self.attempt.answers.get().teacher_score)

    def test_results_action_state_offers_only_view_for_open_attempt(self):
        kwargs = {"can_view_name": False, "review_window_seconds": 0, "identity_window_seconds": 0}
        for status in ("draft", "in_progress"):
            self.attempt.status = status
            self.assertEqual(_resolve_attempt_action_state(self.attempt, **kwargs)["code"], "view", status)
        self.attempt.status = "submitted"
        self.assertEqual(_resolve_attempt_action_state(self.attempt, **kwargs)["code"], "review")


class SupersededAttemptJournalTests(_JournalBridgeSetup):
    """EXA-01 / EX28-06 — rəsmi nəticə ən son bitmiş, sınaq olmayan final cəhdidir."""

    def _finished_written_attempt(self, exam, *, number, started_ago_minutes):
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted", attempt_number=number)
        ExamAttempt.objects.filter(pk=attempt.pk).update(
            started_at=timezone.now() - timedelta(minutes=started_ago_minutes)
        )
        attempt.refresh_from_db()
        ExamAnswer.objects.create(attempt=attempt, question=exam.questions.get(), text_answer="cavab")
        return attempt

    def _grade(self, attempt, score):
        question = attempt.exam.questions.get()
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            apply_manual_grading(attempt_id=attempt.id, grader=self.teacher, payload={f"score_{question.id}": score})

    def test_late_grading_of_older_attempt_does_not_overwrite_later_official_grade(self):
        exam, _question = self._written_exam(points=10)
        first = self._finished_written_attempt(exam, number=1, started_ago_minutes=120)
        second = self._finished_written_attempt(exam, number=2, started_ago_minutes=30)

        self._grade(second, "8")  # 8/10 → 40
        self.assertEqual(self._final_grade().exam_score, Decimal("40"))

        before = _skips(SKIP_SUPERSEDED_ATTEMPT)
        self._grade(first, "2")  # köhnə cəhdin gecikmiş yoxlaması
        self.assertEqual(self._final_grade().exam_score, Decimal("40"))
        self.assertEqual(_skips(SKIP_SUPERSEDED_ATTEMPT), before + 1)

        # Ən son cəhdin yenidən yoxlanması (5 dəq. pəncərəsi daxilində) hələ də yazılır.
        self._grade(second, "6")
        self.assertEqual(self._final_grade().exam_score, Decimal("30"))

    def test_appeal_style_resync_of_older_test_attempt_is_skipped(self):
        older = self._correct_test_attempt()  # 100 %
        ExamAttempt.objects.filter(pk=older.pk).update(started_at=timezone.now() - timedelta(hours=2))
        older.refresh_from_db()
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            older.mark_finished(status="submitted")
        self.assertEqual(self._final_grade().exam_score, Decimal("50"))

        retake = ExamAttempt.objects.create(user=self.student, exam=older.exam, status="in_progress", attempt_number=2)
        ExamAnswer.objects.create(attempt=retake, question=older.exam.questions.get())  # boş → 0 %
        with bypass_rls(), self.captureOnCommitCallbacks(execute=True):
            retake.mark_finished(status="submitted")
        self.assertEqual(self._final_grade().exam_score, Decimal("0"))

        with bypass_rls():
            self.assertIsNone(sync_attempt_to_journal(older, actor=self.teacher))
        self.assertEqual(self._final_grade().exam_score, Decimal("0"))

    def test_later_trial_or_open_attempt_does_not_supersede(self):
        exam, _question = self._written_exam(points=10)
        first = self._finished_written_attempt(exam, number=1, started_ago_minutes=120)
        ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress", attempt_number=2)
        ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted", attempt_number=3, is_trial=True)

        self._grade(first, "8")
        self.assertEqual(self._final_grade().exam_score, Decimal("40"))


@override_settings(CACHES=LOCMEM_CACHE)
class AnswerKeyReleaseTests(TestCase):
    """EX28-03 — cəhd haqqı qalıbsa açar gizli, verdikt/bal görünür."""

    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("a2key")
        cls.exam = _make_quiz(cls.org, cls.teacher, n_questions=1, max_attempts_per_user=2)
        cls.question = cls.exam.questions.get()
        cls.wrong = cls.question.options.get(is_correct=False)

    def _finished_attempt(self, number):
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, attempt_number=number)
        answer = ExamAnswer.objects.create(attempt=attempt, question=self.question)
        answer.selected_options.add(self.wrong)
        attempt.mark_finished(status="submitted")
        return attempt

    def _result(self, attempt):
        client = _student_client("a2key_student", self.org)
        return client.get(reverse("exams:exam_result", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id}))

    def test_key_hidden_while_attempts_left_but_verdict_shown(self):
        first = self._finished_attempt(1)

        response = self._result(first)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["answer_key_hidden"])
        self.assertNotContains(response, "correct-option")
        self.assertNotContains(response, "correct-icon")
        self.assertContains(response, "q-verdict-chip--wrong")

    def test_key_shown_after_last_allowed_attempt(self):
        first = self._finished_attempt(1)
        self._finished_attempt(2)

        response = self._result(first)

        self.assertFalse(response.context["answer_key_hidden"])
        self.assertContains(response, "correct-option")

    def test_second_chance_grant_hides_key_again_and_end_datetime_releases_it(self):
        first = self._finished_attempt(1)
        self._finished_attempt(2)
        self.assertFalse(attempt_answer_key_hidden(first))

        StudentExamAttemptGrant.objects.create(exam=self.exam, student=self.student, extra_attempts=1)
        self.assertTrue(attempt_answer_key_hidden(first))

        after_end = self.exam.end_datetime + timedelta(seconds=1)
        self.assertFalse(attempt_answer_key_hidden(first, now=after_end))

    def test_unlimited_attempts_hide_key_and_trial_shows_it(self):
        Exam.objects.filter(pk=self.exam.pk).update(max_attempts_per_user=None)
        first = self._finished_attempt(1)
        first.exam.refresh_from_db()
        self.assertTrue(attempt_answer_key_hidden(first))

        first.is_trial = True
        self.assertFalse(attempt_answer_key_hidden(first))


@override_settings(CACHES=LOCMEM_CACHE)
class CodingZipTeacherScopeTests(TestCase):
    """EX28-09 — ZIP yalnız imtahan müəllifinə (və imtahan mərkəzinə), org-dakı hər müəllimə yox."""

    def setUp(self):
        self.org, self.teacher, self.student = _make_people("a2zip")
        self.other_teacher = User.objects.create_user("a2zip_other", "a2zip_other@test.az", PASSWORD)
        _assign_user_to_org(self.other_teacher, self.org, ProfileRole.TEACHER)
        self.exam = Exam.objects.create(
            author=self.teacher,
            organization=self.org,
            title="A2 Coding",
            exam_type="coding",
            random_question_count=0,
            is_active=True,
        )
        _, coding_question = upsert_coding_question(
            self.exam,
            payload={
                "language": "python",
                "title": "Hello",
                "problem_statement": "Print hello.",
                "input_description": "",
                "output_description": "",
                "example_input": "",
                "example_output": "hello",
                "time_limit_seconds": 2,
                "memory_limit_mb": 128,
                "max_score": 100,
                "starter_code": "",
                "allow_file_creation": True,
                "allow_multiple_files": True,
                "enable_code_execution": False,
            },
            visible_cases=[],
            hidden_cases=[],
        )
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="submitted")
        submission = CodingSubmission.objects.create(
            student=self.student,
            exam=self.exam,
            attempt=attempt,
            question=coding_question,
            selected_language="python",
            submitted_code="print('hello')",
            files=[{"name": "main.py", "content": "print('hello')", "language": "python", "is_main": True}],
            is_final=True,
            execution_status=CodingSubmission.STATUS_SUBMITTED,
        )
        self.url = reverse(
            "exams:coding_submission_download",
            kwargs={"slug": self.exam.slug, "attempt_id": attempt.id, "submission_id": submission.id},
        )

    def test_unrelated_teacher_of_same_org_cannot_download(self):
        response = _student_client("a2zip_other", self.org).get(self.url)
        self.assertEqual(response.status_code, 404)

    def test_author_and_student_can_download(self):
        self.assertEqual(_student_client("a2zip_teacher", self.org).get(self.url).status_code, 200)
        self.assertEqual(_student_client("a2zip_student", self.org).get(self.url).status_code, 200)
