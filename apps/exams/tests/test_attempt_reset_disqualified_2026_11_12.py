"""«Nəticəni sil» — imtahandan uzaqlaşdırılmış (``supervision_status=removed``) cəhd (sahib 2026-11-12).

Nəticələr səhifəsində «İmtahandan uzaqlaşdırılıb» statuslu midterm cəhdi (536 T, 16/30) həm sətir düyməsi, həm də
«Seçilmişlərin nəticəsini sil» ilə silinəndə HTTP 500. Testlər real uzaqlaşdırma yollarını keçir (müəllim
``teacher_stop_attempt``, zal ``remove_student``, pozuntu limiti): cavablar, nəzarət hadisəsi, proktorinq qeydi və
jurnalın midterm xanası (0) yaranır; sonra JS-in göndərdiyi eyni sorğu (``attempt_ids`` / ``attempt_id`` /
``select_scope=all_matching`` + ``reason``) prod şəraitində (``ATOMIC_REQUESTS`` + ``rls_app_role``) göndərilir.

Gözlənilməz xəta (məs. COMMIT-ə qədər təxirə salınmış FK pozuntusu) artıq 500 vermir: həmin cəhd yerində qalır,
səbəb mesajla göstərilir, eyni sorğudakı digər cəhdlər sıfırlanır (``attempt_reset.service``).
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from unittest import mock

from django.db import connection
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.exams.domain.final_center import TICKET_STATUS_ACTIVE, TICKET_STATUS_ASSIGNED, TICKET_STATUS_REMOVED
from apps.exams.models import ExamAnswer, ExamAttempt, FinalExamTicket, ProctoringLog, SupervisionIncident
from apps.exams.services import attempt_reset, exam_attempt_purge
from apps.exams.services.final_center import begin_attempt_for_ticket, enter_waiting, remove_student, start_room
from apps.exams.services.supervision.actions import teacher_stop_attempt
from apps.exams.tests.test_attempt_reset_2026_11_04 import REASON, _ResetSetup
from apps.exams.tests.test_final_center_reopen_2026_11_04 import _ReopenBase
from core.rls import bypass_rls


@contextmanager
def prod_request_conditions():
    """Prod kimi: ``ATOMIC_REQUESTS`` (bütün sorğu bir tranzaksiya) + tətbiq rolu (RLS siyasətləri işləyir)."""
    with mock.patch.dict(connection.settings_dict, {"ATOMIC_REQUESTS": True}):
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE rls_app_role")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")


class _DisqualifiedBase(_ResetSetup):
    def setUp(self):
        super().setUp()
        self.exam_dq, self.options_dq = self._exam(title="MT Disqualified")
        self.removed = self._removed_attempt(self.exam_dq, self.options_dq, correct=2)

    def _removed_attempt(self, exam, options, *, correct):
        """Real yol: başlanmış cəhd → cavablar + proktorinq → müəllim «uzaqlaşdır» (``teacher_stop_attempt``)."""
        with bypass_rls():
            attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress")
            for index, (question, right, wrong) in enumerate(options):
                answer = ExamAnswer.objects.create(attempt=attempt, question=question)
                answer.selected_options.add(right if index < correct else wrong)
            ProctoringLog.objects.create(exam_attempt=attempt, event_type="tab_switch")
            with self.captureOnCommitCallbacks(execute=True):
                teacher_stop_attempt(attempt, self.teacher, reason="Köçürmə", action="removed")
            attempt.refresh_from_db()
        return attempt

    def _post(self, payload, exam=None, follow=False):
        exam = exam or self.exam_dq
        client = self._client(self.center_head)
        client.raise_request_exception = True
        with self.captureOnCommitCallbacks(execute=True), prod_request_conditions():
            return client.post(
                reverse("exams:reset_exam_attempts", kwargs={"slug": exam.slug}),
                {"reason": REASON, **payload},
                follow=follow,
            )

    @staticmethod
    def _messages(response):
        return [str(message) for message in response.context["messages"]]

    def _midterm_cell(self):
        row = self._score_row()
        return None if row is None else (row.score, (row.exam_source or {}).get("attempt_id"))


class DisqualifiedAttemptResetTests(_DisqualifiedBase):
    def test_fixture_is_disqualified_with_incident_and_journal_zero(self):
        self.assertEqual(self.removed.supervision_status, "removed")
        self.assertTrue(self.removed.is_finished)
        with bypass_rls():
            self.assertTrue(SupervisionIncident.objects.filter(attempt=self.removed).exists())
        self.assertEqual(self._midterm_cell(), (Decimal("0"), self.removed.pk))

    def test_row_reset_of_disqualified_attempt(self):
        response = self._post({"attempt_ids": [str(self.removed.pk)]})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._exists(self.removed))
        with bypass_rls():
            self.assertFalse(SupervisionIncident.objects.filter(attempt_id=self.removed.pk).exists())
            self.assertNotEqual(self.exam_dq.attempts_left_for(self.student), 0)  # yenidən vermək olar
            self.assertFalse(self.exam_dq._user_has_active_attempt(self.student))
        # Midterm xanası: digər imtahanın (``self.exam``) rəsmi cəhdi eyni xanaya yazılır → ona qayıdır.
        cell = self._midterm_cell()
        self.assertNotEqual(cell and cell[1], self.removed.pk)
        rows = [row for row in self._reset_rows() if row.resource_id == str(self.removed.pk)]
        self.assertEqual(len(rows), 1)
        before = rows[0].changes["scores_before"]
        self.assertEqual(before["supervision_status"], "removed")
        self.assertTrue(before["score"] and before["max_score"] and before["percent"], before)

    def test_single_attempt_id_payload(self):
        response = self._post({"attempt_id": str(self.removed.pk)})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._exists(self.removed))

    def test_only_attempt_clears_midterm_cell(self):
        with bypass_rls():
            ExamAttempt.objects.filter(exam=self.exam).delete()
        self._post({"attempt_ids": [str(self.removed.pk)]})
        self.assertFalse(self._exists(self.removed))
        self.assertIsNone(self._score_row())

    def test_all_matching_and_already_reset_attempt(self):
        response = self._post({"select_scope": "all_matching", "filter_query": "", "expected_count": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._exists(self.removed))
        again = self._post({"attempt_ids": [str(self.removed.pk)]})
        self.assertEqual(again.status_code, 302)

    def test_mixed_selection_in_one_post(self):
        normal = self._finish(self.exam_dq, self.options_dq, correct=3, attempt_number=2)
        response = self._post({"attempt_ids": [str(self.removed.pk), str(normal.pk), "999999999"]})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._exists(self.removed))
        self.assertFalse(self._exists(normal))

    def test_service_result(self):
        result = attempt_reset.reset_attempt(self.removed, actor=self.center_head, reason=REASON)
        self.assertEqual(result.status, attempt_reset.STATUS_RESET)


class DisqualifiedCenterAttemptResetTests(_ReopenBase):
    """Zal imtahanı: nəzarətçi tələbəni «uzaqlaşdırır» (``remove_student``) → bilet ``removed`` → sıfırlama."""

    def _removed_attempt(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        attempt = begin_attempt_for_ticket(self.ticket)
        self.ticket.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(remove_student(self.ticket, self.invigilator, action="removed", reason="Köçürmə"))
        attempt.refresh_from_db()
        self.ticket.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "removed")
        self.assertEqual(self.ticket.status, TICKET_STATUS_REMOVED)
        return attempt

    def test_center_head_resets_removed_attempt_and_ticket_reopens(self):
        attempt = self._removed_attempt()
        client = self._client_for(self.center)
        client.raise_request_exception = True
        with self.captureOnCommitCallbacks(execute=True), prod_request_conditions():
            response = client.post(
                reverse("exams:reset_exam_attempts", kwargs={"slug": self.exam.slug}),
                {"attempt_ids": [str(attempt.pk)], "reason": REASON},
            )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ExamAttempt.objects.filter(pk=attempt.pk).exists())
        ticket = FinalExamTicket.objects.get(pk=self.ticket.pk)
        self.assertEqual(ticket.status, TICKET_STATUS_ASSIGNED)
        self.assertIsNone(ticket.attempt_id)
        self.assertEqual(ticket.removal_action, "")
        self.assertIsNone(ticket.removed_at)
        self.assertIsNone(ticket.removed_by_id)
        audit = AuditLog.objects.filter(
            resource_type="final_exam_ticket",
            resource_id=str(ticket.pk),
            reason="final_ticket_reset_after_attempt_purge",
        ).get()
        self.assertEqual(audit.changes["previous_attempt_id"], attempt.pk)
        self.assertEqual(audit.changes["previous_status"], TICKET_STATUS_REMOVED)
        self.assertEqual(audit.changes["previous_removal_action"], "removed")
        # Tələbə yenidən başlaya bilir.
        enter_waiting(ticket, language="")
        ticket.refresh_from_db()
        new_attempt = begin_attempt_for_ticket(ticket)
        self.assertNotEqual(new_attempt.pk, attempt.pk)
        self.assertEqual(FinalExamTicket.objects.get(pk=ticket.pk).status, TICKET_STATUS_ACTIVE)


class DisqualifiedVariantsResetTests(_ResetSetup):
    """Başqa uzaqlaşdırma yolları: pozuntu limiti (cəhd bitməmiş qalır), cavabsız suallar, əl ilə düzəldilmiş xana."""

    def _post(self, exam, attempt_ids):
        client = self._client(self.center_head)
        client.raise_request_exception = True
        with self.captureOnCommitCallbacks(execute=True), prod_request_conditions():
            return client.post(
                reverse("exams:reset_exam_attempts", kwargs={"slug": exam.slug}),
                {"attempt_ids": [str(pk) for pk in attempt_ids], "reason": REASON},
            )

    def test_violation_limit_removed_unfinished_attempt(self):
        from apps.exams.services.supervision.incidents import _log_system_incident

        exam, options = self._exam(title="MT Violation")
        with bypass_rls():
            attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress")
            ExamAnswer.objects.create(attempt=attempt, question=options[0][0]).selected_options.add(options[0][1])
            attempt.supervision_status = "removed"
            attempt.save(update_fields=["supervision_status"])
            _log_system_incident(attempt, "auto_locked", {"reason": "student_removed", "violation_count": 3})
        response = self._post(exam, [attempt.pk])
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._exists(attempt))

    def test_removed_attempt_with_unanswered_questions(self):
        exam, options = self._exam(title="MT Unanswered", questions=6)
        with bypass_rls():
            attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress")
            for index, (question, right, wrong) in enumerate(options):
                answer = ExamAnswer.objects.create(attempt=attempt, question=question)
                if index < 2:
                    answer.selected_options.add(right)
                elif index < 4:
                    answer.selected_options.add(wrong)
            with self.captureOnCommitCallbacks(execute=True):
                teacher_stop_attempt(attempt, self.teacher, reason="Köçürmə")
        response = self._post(exam, [attempt.pk])
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._exists(attempt))


class ResetFaultIsolationTests(_DisqualifiedBase):
    """Gözlənilməz xəta → 500 yox: cəhd yerində qalır, mesaj göstərilir, digər seçilmişlər sıfırlanır."""

    def _orphan_after_delete(self):
        """``_restore_journal``-dan sonra silinmiş cəhdə işarə edən sətir — COMMIT-ə qədər təxirə salınmış FK pozuntusu
        (RLS-in gizlətdiyi və ya kaskadın tutmadığı uşaq sətrin modeli)."""
        original = exam_attempt_purge._restore_journal
        target = self.removed.pk

        def restore(attempt, plan):
            original(attempt, plan)
            if int(plan.info["attempt_id"]) == target:  # ``attempt.pk`` silinmədən sonra None-dır
                with bypass_rls():  # RLS-in WITH CHECK-i yox — məhz təxirə salınmış FK yoxlanışı sınanır
                    ProctoringLog.objects.create(exam_attempt_id=target, event_type="tab_switch")

        return mock.patch.object(exam_attempt_purge, "_restore_journal", side_effect=restore)

    def test_deferred_fk_violation_is_reported_not_500_and_others_reset(self):
        other = self._finish(self.exam_dq, self.options_dq, correct=3, attempt_number=2)
        with self._orphan_after_delete():
            response = self._post({"attempt_ids": [str(self.removed.pk), str(other.pk)]}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._exists(self.removed))  # savepoint geri qayıtdı — cəhd və xana toxunulmaz
        self.assertEqual(self._midterm_cell(), (Decimal("0"), self.removed.pk))
        with bypass_rls():
            self.assertTrue(SupervisionIncident.objects.filter(attempt=self.removed).exists())
        self.assertFalse(self._exists(other))  # eyni sorğudakı digər cəhd sıfırlandı
        texts = self._messages(response)
        self.assertTrue(any(f"#{self.removed.pk}" in text for text in texts), texts)
        self.assertEqual([row.resource_id for row in self._reset_rows()], [str(other.pk)])

    def test_unexpected_exception_in_service_returns_failed_status(self):
        with mock.patch.object(exam_attempt_purge, "_audit", side_effect=RuntimeError("boom")):
            result = attempt_reset.reset_attempt(self.removed, actor=self.center_head, reason=REASON)
        self.assertEqual(result.status, attempt_reset.STATUS_FAILED)
        self.assertEqual(result.blockers, (attempt_reset.FAILED_BLOCKER,))
        self.assertTrue(self._exists(self.removed))
        # Sonra adi sıfırlama işləyir (tranzaksiya «aborted» qalmayıb).
        self.assertEqual(
            attempt_reset.reset_attempt(self.removed, actor=self.center_head, reason=REASON).status,
            attempt_reset.STATUS_RESET,
        )

    def test_group_preview_survives_plan_error(self):
        with mock.patch.object(exam_attempt_purge, "build_plan", side_effect=RuntimeError("boom")):
            preview = attempt_reset.preview_attempts([self.removed])
        self.assertEqual(preview["blocked"], 1)
        self.assertEqual(preview["blockers"], {attempt_reset.FAILED_BLOCKER: 1})

    def test_malformed_ids_are_ignored_not_500(self):
        response = self._post({"attempt_ids": ["²", "99999999999999999999999", "-3", " "]}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._exists(self.removed))
