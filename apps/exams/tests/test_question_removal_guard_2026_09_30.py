"""QB 2026-09-30 — «son aktiv suallar» qoruyucusu: servis qatı.

Sahib: canlı imtahandan sonra bütün aktiv sualları seçib silmək istəyəndə
«Aktiv imtahanın son aktiv sualı silinə bilməz…» xətası çıxırdı («aktiv
istifadəçi yoxdur axı»). Qayda qalır (dərc olunmuş imtahanda ən azı bir aktiv
sual), amma indi təsdiqlə imtahan deaktiv edilir və suallar BİR tranzaksiyada
silinir/deaktiv edilir — imtahanı hazırda kimsə işlədirsə (açıq cəhd, canlı
sessiya, final zal oturumu) imtina edilir.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.exams.domain.final_center.states import ROOM_SESSION_STATE_ACTIVE, TICKET_STATUS_WAITING
from apps.exams.models import Exam, ExamAttempt, ExamQuestion, ExamRoom, ExamRoomSession, FinalExamTicket
from apps.exams.services.question_invariants import (
    MODE_DEACTIVATE,
    MODE_DELETE,
    ActiveExamRequiresQuestion,
    ExamInUse,
    active_exam_question_invariant_message,
    delete_exam_questions,
    remove_exam_questions,
)
from apps.live_exam.models import LiveAnswer, LivePlayer, LiveSession
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class _GuardFixture(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("qb_guard_teacher", "qb_guard_teacher@example.com", "pw")
        self.student = User.objects.create_user("qb_guard_student", "qb_guard_student@example.com", "pw")
        self.org = Organization.objects.create(
            name="QB guard org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )

    def _exam(self, *, active=True, question_count=3, **extra):
        exam = Exam.objects.create(
            title="QB guard exam",
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            is_active=active,
            **extra,
        )
        questions = [
            ExamQuestion.objects.create(exam=exam, order=index + 1, text=f"Sual {index + 1}", points=1)
            for index in range(question_count)
        ]
        return exam, questions

    def _attempt(self, exam, *, status="in_progress", trial=False):
        number = ExamAttempt.objects.filter(user=self.student, exam=exam).count() + 1
        return ExamAttempt.objects.create(
            user=self.student, exam=exam, status=status, is_trial=trial, attempt_number=number
        )

    def _ids(self, questions):
        return [question.pk for question in questions]


class QuestionRemovalGuardTests(_GuardFixture):
    def test_subset_of_active_exam_is_deleted_without_confirmation(self):
        exam, questions = self._exam()

        outcome = remove_exam_questions(exam, self._ids(questions[:2]), mode=MODE_DELETE)

        self.assertEqual(outcome.count, 2)
        self.assertFalse(outcome.exam_deactivated)
        self.assertEqual(list(exam.questions.values_list("pk", flat=True)), [questions[2].pk])
        exam.refresh_from_db()
        self.assertTrue(exam.is_active)

    def test_all_active_questions_require_confirmation_and_change_nothing(self):
        exam, questions = self._exam()

        with self.assertRaises(ActiveExamRequiresQuestion) as ctx:
            remove_exam_questions(exam, self._ids(questions), mode=MODE_DELETE)

        # Geriyə uyğunluq: köhnə çağıranlar ValidationError tuturdu.
        self.assertIsInstance(ctx.exception, ValidationError)
        self.assertEqual(ctx.exception.code, "active_exam_requires_question")
        self.assertEqual(exam.questions.count(), 3)
        exam.refresh_from_db()
        self.assertTrue(exam.is_active)

    def test_confirmed_delete_deactivates_exam_in_same_transaction_with_audit(self):
        exam, questions = self._exam()

        outcome = remove_exam_questions(
            exam, self._ids(questions), mode=MODE_DELETE, deactivate_exam=True, by_user=self.teacher
        )

        self.assertEqual(outcome.count, 3)
        self.assertTrue(outcome.exam_deactivated)
        self.assertFalse(exam.is_active)  # çağıranın nüsxəsi də yenilənir
        exam.refresh_from_db()
        self.assertFalse(exam.is_active)
        self.assertEqual(exam.questions.count(), 0)
        self.assertTrue(AuditLog.objects.filter(reason="exam_unpublished", object_id=str(exam.pk)).exists())

    def test_confirmed_deactivate_mode_deactivates_questions_and_exam(self):
        exam, questions = self._exam()

        outcome = remove_exam_questions(exam, self._ids(questions), mode=MODE_DEACTIVATE, deactivate_exam=True)

        self.assertEqual(outcome.count, 3)
        self.assertTrue(outcome.exam_deactivated)
        self.assertFalse(exam.questions.filter(is_active=True).exists())
        self.assertEqual(exam.questions.count(), 3)

    def test_confirmation_flag_is_ignored_when_active_questions_remain(self):
        exam, questions = self._exam()

        outcome = remove_exam_questions(exam, self._ids(questions[:1]), mode=MODE_DELETE, deactivate_exam=True)

        self.assertFalse(outcome.exam_deactivated)
        exam.refresh_from_db()
        self.assertTrue(exam.is_active)

    def test_inactive_questions_are_not_counted_as_last_active(self):
        exam, questions = self._exam()
        ExamQuestion.objects.filter(pk__in=self._ids(questions[1:])).update(is_active=False)

        # Yalnız deaktiv suallar seçilib — aktiv sual qalır, təsdiq lazım deyil.
        self.assertEqual(delete_exam_questions(exam, self._ids(questions[1:])), 2)
        # Tək aktiv sual + deaktivlər birlikdə seçiləndə isə təsdiq tələb olunur.
        with self.assertRaises(ActiveExamRequiresQuestion):
            delete_exam_questions(exam, self._ids(questions[:1]))

    def test_active_questions_of_other_language_keep_exam_published(self):
        exam, questions = self._exam()
        ExamQuestion.objects.filter(pk=questions[2].pk).update(language="ru")

        self.assertEqual(delete_exam_questions(exam, self._ids(questions[:2])), 2)
        exam.refresh_from_db()
        self.assertTrue(exam.is_active)

    def test_draft_exam_never_needs_confirmation(self):
        exam, questions = self._exam(active=False)

        outcome = remove_exam_questions(exam, self._ids(questions), mode=MODE_DELETE)

        self.assertEqual(outcome.count, 3)
        self.assertFalse(outcome.exam_deactivated)

    def test_invariant_message_names_the_exam_not_users(self):
        message = active_exam_question_invariant_message()
        self.assertIn("imtahan", message)
        self.assertNotIn("istifadəçi", message)

    def test_audit_failure_rolls_back_questions_and_exam(self):
        exam, questions = self._exam()

        with patch("apps.audit.public.log_action", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaises(RuntimeError):
                remove_exam_questions(exam, self._ids(questions), mode=MODE_DELETE, deactivate_exam=True)

        exam.refresh_from_db()
        self.assertTrue(exam.is_active)
        self.assertEqual(exam.questions.count(), 3)


class QuestionRemovalExamInUseTests(_GuardFixture):
    def _assert_refused(self, exam, questions, *, fragment):
        with self.assertRaises(ExamInUse) as ctx:
            remove_exam_questions(exam, self._ids(questions), mode=MODE_DELETE, deactivate_exam=True)
        self.assertEqual(ctx.exception.code, "exam_in_use")
        self.assertIn(fragment, " ".join(ctx.exception.messages))
        exam.refresh_from_db()
        self.assertTrue(exam.is_active)
        self.assertEqual(exam.questions.count(), len(questions))

    def test_in_progress_attempt_refuses_even_with_confirmation(self):
        exam, questions = self._exam()
        self._attempt(exam, status="in_progress")

        self._assert_refused(exam, questions, fragment="1")

    def test_in_progress_attempt_refusal_comes_before_confirmation_prompt(self):
        exam, questions = self._exam()
        self._attempt(exam, status="draft")

        with self.assertRaises(ExamInUse):
            remove_exam_questions(exam, self._ids(questions), mode=MODE_DELETE)

    def test_in_progress_attempt_blocks_subset_delete_but_not_deactivate(self):
        # Təhlükəsizlik baxışı 2026-09-30 (H2): yazılan imtahandan sual SİLMƏK
        # tələbənin cavabını da silərdi — indi rədd edilir; deaktivasiya qalır.
        exam, questions = self._exam()
        self._attempt(exam, status="in_progress")

        with self.assertRaises(ExamInUse):
            delete_exam_questions(exam, self._ids(questions[:1]))
        self.assertEqual(remove_exam_questions(exam, self._ids(questions[:1]), mode=MODE_DEACTIVATE).count, 1)

    def test_finished_and_trial_attempts_do_not_block(self):
        exam, questions = self._exam()
        self._attempt(exam, status="submitted")
        self._attempt(exam, status="expired")
        trial = ExamAttempt.objects.create(
            user=self.teacher, exam=exam, status="in_progress", is_trial=True, attempt_number=1
        )

        outcome = remove_exam_questions(exam, self._ids(questions), mode=MODE_DELETE, deactivate_exam=True)

        self.assertTrue(outcome.exam_deactivated)
        self.assertTrue(ExamAttempt.objects.filter(pk=trial.pk).exists())

    def test_in_progress_attempt_past_its_deadline_does_not_block(self):
        exam, questions = self._exam(total_duration_minutes=30)
        attempt = self._attempt(exam, status="in_progress")
        ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(hours=3))

        outcome = remove_exam_questions(exam, self._ids(questions), mode=MODE_DELETE, deactivate_exam=True)

        self.assertTrue(outcome.exam_deactivated)

    def test_running_live_session_refuses_and_names_pin(self):
        exam, questions = self._exam()
        session = LiveSession.objects.create(exam=exam, host_user=self.teacher, state=LiveSession.STATE_REVEAL)

        self._assert_refused(exam, questions, fragment=session.pin)

    def test_finished_live_session_does_not_block(self):
        """Sahibin halı: canlı imtahan bitib, oyunçu cavabları qalıb — təmizləmə mümkündür."""
        exam, questions = self._exam(question_count=10)
        session = LiveSession.objects.create(exam=exam, host_user=self.teacher, state=LiveSession.STATE_FINISHED)
        player = LivePlayer.objects.create(session=session, nickname="Aysel", client_id="c-1", score=900)
        LiveAnswer.objects.create(session=session, player=player, question_id=questions[0].pk, is_correct=True)

        outcome = remove_exam_questions(exam, self._ids(questions), mode=MODE_DELETE, deactivate_exam=True)

        self.assertEqual(outcome.count, 10)
        self.assertTrue(outcome.exam_deactivated)
        # Canlı nəticələr (oyunçu/cavab) toxunulmaz qalır.
        self.assertTrue(LiveAnswer.objects.filter(session=session).exists())

    def test_abandoned_stale_live_session_does_not_block(self):
        exam, questions = self._exam()
        session = LiveSession.objects.create(exam=exam, host_user=self.teacher)
        LiveSession.objects.filter(pk=session.pk).update(created_at=timezone.now() - timedelta(hours=8))

        outcome = remove_exam_questions(exam, self._ids(questions), mode=MODE_DELETE, deactivate_exam=True)

        self.assertTrue(outcome.exam_deactivated)

    def test_ongoing_final_hall_session_refuses(self):
        exam, questions = self._exam()
        now = timezone.now()
        room = ExamRoom.objects.create(organization=self.org, name="QB zal", code="QBZ", capacity=10)
        hall = ExamRoomSession.objects.create(
            organization=self.org,
            room=room,
            scheduled_start=now - timedelta(hours=1),
            scheduled_end=now + timedelta(hours=1),
            state=ROOM_SESSION_STATE_ACTIVE,
            started_at=now - timedelta(minutes=10),
        )
        FinalExamTicket.objects.create(
            organization=self.org, session=hall, exam=exam, student=self.student, status=TICKET_STATUS_WAITING
        )

        self._assert_refused(exam, questions, fragment="1")
