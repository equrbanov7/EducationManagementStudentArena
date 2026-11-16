"""Sahib 2026-11-16: imtahan nəticəsinin ləğvi.

* «Uzaqlaşdırılmış / qovulmuş tələbənin midterm nəticəsi ləğv olmalıdır, qeyd kimi də düşməlidir».
* «Nəzarətçi uzaqlaşdırana kimi tələbə “Bitir” vurur, bal düşür — o balı izahatla ləğv edib “köçürdü” və ya başqa
  səbəb kimi qeyd etmək olmalıdır».

Ləğv: jurnalda 0 bal, cəhd silinmir, tələbəyə «Nəticəniz ləğv olunub» qeydi (səbəb + izahat), audit izi.
"""

from __future__ import annotations

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.exams.domain.final_center import TICKET_STATUS_COMPLETED
from apps.exams.models import ExamAttempt, FinalExamTicket, SupervisionIncident
from apps.exams.services.final_center import TicketStateError, annul_attempt_result, is_annulled
from apps.exams.services.supervision.interventions import attach_attempt_interventions, get_attempt_intervention
from core.rls import bypass_rls

from .test_final_center_flow import _FlowBase
from .test_midterm_journal_sync_2026_10_21 import _MidtermSetup


class MidtermResultAnnulTests(_MidtermSetup):
    def test_annul_after_submit_writes_zero_and_shows_note(self):
        attempt = self._finish(*self._exam(), correct=3)
        self.assertEqual(self._score_row().score, Decimal("30"))
        with bypass_rls():
            done = annul_attempt_result(attempt, self.teacher, reason_key="cheating", note="Telefondan köçürürdü")
            attempt.refresh_from_db()
        self.assertTrue(done)
        self.assertEqual(attempt.supervision_status, "removed")
        self.assertEqual(self._score_row().score, Decimal("0"))
        with bypass_rls():
            intervention = get_attempt_intervention(attempt)
            self.assertTrue(
                AuditLog.objects.filter(
                    resource_id=str(attempt.pk), reason__startswith="exam_result_annulled[cheating]"
                ).exists()
            )
        self.assertEqual(intervention["action"], "annulled")
        self.assertTrue(intervention["is_annulled"])
        self.assertIn("Köçürmə", intervention["reason"])
        self.assertIn("Telefondan köçürürdü", intervention["reason"])
        with bypass_rls():
            listed = attach_attempt_interventions([ExamAttempt.objects.get(pk=attempt.pk)])[0]
        self.assertEqual(listed.exam_intervention["action"], "annulled")

        with bypass_rls():
            self.assertFalse(annul_attempt_result(attempt, self.teacher, reason_key="other", note="təkrar"))
            self.assertEqual(
                SupervisionIncident.objects.filter(attempt=attempt, teacher_action="result_annulled").count(), 1
            )

    def test_note_and_reason_are_required(self):
        attempt = self._finish(*self._exam(), correct=3)
        with bypass_rls():
            with self.assertRaises(TicketStateError):
                annul_attempt_result(attempt, self.teacher, reason_key="cheating", note="  ")
            with self.assertRaises(TicketStateError):
                annul_attempt_result(attempt, self.teacher, reason_key="bogus", note="x")
            self.assertFalse(is_annulled(attempt))
        self.assertEqual(self._score_row().score, Decimal("30"))

    def test_removed_attempt_shows_annulled_note_and_command_rewrites_zero(self):
        attempt = self._finish(*self._exam(), correct=3)
        with bypass_rls():
            # Köhnə hal: qovulma qeyd olunub, amma jurnaldakı bal yenidən yazılmayıb.
            ExamAttempt.objects.filter(pk=attempt.pk).update(supervision_status="removed")
            attempt.refresh_from_db()
            self.assertTrue(get_attempt_intervention(attempt)["is_annulled"])
        self.assertEqual(self._score_row().score, Decimal("30"))

        out = StringIO()
        with bypass_rls():
            call_command("annul_removed_exam_results_20261116", stdout=out)
        self.assertIn("mode=dry_run", out.getvalue())
        self.assertIn("kind=midterm status=written n=1", out.getvalue())
        self.assertEqual(self._score_row().score, Decimal("30"))

        out = StringIO()
        with bypass_rls():
            call_command("annul_removed_exam_results_20261116", "--apply", stdout=out)
        self.assertIn("kind=midterm status=written n=1", out.getvalue())
        self.assertEqual(self._score_row().score, Decimal("0"))

        out = StringIO()
        with bypass_rls():
            call_command("annul_removed_exam_results_20261116", "--apply", stdout=out)
        self.assertIn("kind=midterm status=unchanged n=1", out.getvalue())


class CenterAnnulViewTests(_FlowBase):
    def _completed_attempt(self):
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
        attempt.mark_finished(status="submitted")
        FinalExamTicket.objects.filter(pk=self.ticket.pk).update(status=TICKET_STATUS_COMPLETED, attempt=attempt)
        return attempt

    def _url(self):
        return reverse(
            "exams:exam_center_ticket_annul", kwargs={"session_id": self.session.pk, "ticket_id": self.ticket.pk}
        )

    def test_center_annuls_completed_ticket_with_note(self):
        attempt = self._completed_attempt()
        detail = self._client_for(self.center).get(
            reverse("exams:exam_center_session_detail", kwargs={"session_id": self.session.pk})
        )
        self.assertContains(detail, "Nəticəni ləğv et")
        response = self._client_for(self.center).post(self._url(), {"reason": "cheating", "note": "Bitir vurdu"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(is_annulled(attempt))
        detail = self._client_for(self.center).get(
            reverse("exams:exam_center_session_detail", kwargs={"session_id": self.session.pk})
        )
        self.assertContains(detail, "Nəticə ləğv olunub")

    def test_missing_note_is_rejected(self):
        attempt = self._completed_attempt()
        self._client_for(self.center).post(self._url(), {"reason": "cheating", "note": ""})
        self.assertFalse(is_annulled(attempt))

    def test_invigilator_cannot_annul(self):
        attempt = self._completed_attempt()
        response = self._client_for(self.invigilator).post(self._url(), {"reason": "cheating", "note": "x"})
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertFalse(is_annulled(attempt))
