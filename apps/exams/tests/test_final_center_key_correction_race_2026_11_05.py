"""Zalı bitirmə + açar düzəlişi: real end_room yolu parent Exam kilidini tutmamalıdır."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

import pytest

from apps.appeals.models import KeyCorrectionCredit
from apps.appeals.services import key_corrections as keys
from apps.appeals.services.scoring import effective_test_score
from apps.exams import score_adjustments
from apps.exams.models import ExamRoom, ExamRoomSession, FinalExamTicket
from apps.exams.services.final_center import sessions
from core.rls import bypass_rls


@pytest.mark.postgres
class FinalCenterKeyCorrectionRaceTests(TransactionTestCase):
    def _attempt(self, *, finished):
        from apps.appeals.tests.test_key_correction_completion_races import KeyCompletionRaceTests

        return KeyCompletionRaceTests._attempt(self, finished=finished)

    def setUp(self):
        from apps.appeals.tests.test_key_correction_completion_races import KeyCompletionRaceTests

        KeyCompletionRaceTests.setUp(self)
        now = timezone.now()
        with bypass_rls():
            room = ExamRoom.objects.create(
                organization=self.org, name="Key race hall", code="KEY", created_by=self.user
            )
            self.session = ExamRoomSession.objects.create(
                organization=self.org,
                room=room,
                state="active",
                scheduled_start=now - timedelta(minutes=1),
                scheduled_end=now + timedelta(hours=1),
                started_at=now,
            )
            self.ticket = FinalExamTicket.objects.create(
                organization=self.org,
                session=self.session,
                exam=self.exam,
                attempt=self.pending,
                student=self.user,
                status="active",
                pin_cipher="temporary-test-cipher",
            )
            self.snapshot = self.pending.answers.get().question_snapshot

    def _worker(self, function):
        def run():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                with bypass_rls():
                    return function()
            finally:
                close_old_connections()

        return run

    def test_apply_and_actual_end_room_do_not_deadlock_or_lose_credit(self):
        scanned, finishing = Event(), Event()
        original_scan = keys._question_answers
        original_finish = score_adjustments.finish_corrections

        def scan_while_room_is_finishing(question):
            answers = original_scan(question)
            scanned.set()  # apply artıq sualın FOR UPDATE kilidini saxlayır
            if not finishing.wait(5):
                raise RuntimeError("room finish did not start")
            return answers

        def signal_finish(attempt):
            if attempt.pk == self.pending.pk:
                finishing.set()  # end_room artıq öz SELECT FOR UPDATE-ni icra edib
            return original_finish(attempt)

        def apply():
            return keys.apply_key_correction(
                self.item, reviewer=self.user, corrected_option_ids=[self.new.pk], reason="Verified answer source"
            )

        with (
            patch.object(keys, "_question_answers", side_effect=scan_while_room_is_finishing),
            patch.object(score_adjustments, "finish_corrections", side_effect=signal_finish),
            patch.object(sessions, "broadcast_to_students"),
            patch.object(sessions, "broadcast_to_staff"),
            ThreadPoolExecutor(2) as pool,
        ):
            applying = pool.submit(self._worker(apply))
            self.assertTrue(scanned.wait(5))
            ending = pool.submit(self._worker(lambda: sessions.end_room(self.session, self.user)))
            correction = applying.result(timeout=15)
            self.assertTrue(ending.result(timeout=15))

        with bypass_rls():
            self.pending.refresh_from_db()
            self.session.refresh_from_db()
            self.ticket.refresh_from_db()
            self.assertEqual(self.pending.status, "submitted")
            self.assertEqual(self.session.state, "ended")
            self.assertEqual(self.ticket.status, "completed")
            self.assertEqual(self.ticket.pin_cipher, "")
            self.assertEqual(KeyCorrectionCredit.objects.filter(correction=correction).count(), 2)
            self.assertEqual(KeyCorrectionCredit.objects.filter(attempt=self.pending, reverted=False).count(), 1)
            self.assertEqual(effective_test_score(self.pending)["effective_score"], 1)
            self.assertEqual(self.pending.answers.get().question_snapshot, self.snapshot)
