"""«Nəticəni sil (cəhdi sıfırla)» + «Qrup cəhdlərini sıfırla» (sahib 2026-11-04).

«Mənə imtahan nəticəsini silmək lazımdır; midterm/final fərq etməsin … səbəb yazaraq yalnız RİM rəhbəri və
imtahan mərkəzi rəhbəri silə bilsin və izləmədə (audit) düşsün. Sonra o cəhd sıfırlanmış sayılsın və midterm
yenidən vermək olsun. Qrupda da elə bir şey etmək olsun». Bax ``apps/exams/services/attempt_reset/``.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import Client
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.exams.domain.final_center import TICKET_STATUS_ACTIVE, TICKET_STATUS_ASSIGNED
from apps.exams.domain.unit_scope_filters import unit_filter_value
from apps.exams.models import ExamAttempt, FinalExamTicket
from apps.exams.services import attempt_reset, exam_attempt_purge
from apps.exams.services.final_center import begin_attempt_for_ticket, enter_waiting
from apps.exams.tests.test_final_center_reopen_2026_11_04 import _ReopenBase
from apps.exams.tests.test_purge_exam_attempt_2026_10_25 import _AttemptPurgeSetup
from apps.organizations.models import Membership
from apps.registrar.models import AssessmentScheme
from core.rls import bypass_rls

REASON = "Tələbə səhvən daxil olub — cəhd sıfırlanır"


class _ResetSetup(_AttemptPurgeSetup):
    """Midterm (2 cəhd: 10/30 və 20/30) + rollar: mərkəz rəhbəri, RİM rəhbəri, mərkəz işçisi, müəllim."""

    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        with bypass_rls():
            self.exam.max_attempts_per_user = 2
            self.exam.save(update_fields=["max_attempts_per_user"])
            self.center_head = self._member(user_model, "ar_center_head", "exam_center_head")
            self.rim_head = self._member(user_model, "ar_rim_head", "ikt_rehber")
            self.center_staff = self._member(user_model, "ar_center_staff", "exam_center_staff")

    def _member(self, user_model, username, role_name):
        user = user_model.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=user,
            organization=self.org,
            role=self.org.roles.get(name=role_name),
            is_primary=True,
            is_active=True,
        )
        return user

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _post_reset(self, user, attempt_ids, reason=REASON):
        with self.captureOnCommitCallbacks(execute=True):
            return self._client(user).post(
                reverse("exams:reset_exam_attempts", kwargs={"slug": self.exam.slug}),
                {"attempt_ids": [str(pk) for pk in attempt_ids], "reason": reason},
            )

    def _left(self):
        with bypass_rls():
            return self.exam.attempts_left_for(self.student)

    def _reset_rows(self):
        with bypass_rls():
            return list(
                AuditLog.objects.filter(
                    resource_type=exam_attempt_purge.AUDIT_RESOURCE_TYPE, changes__verb=attempt_reset.RESET_VERB
                )
            )


class AttemptResetRbacTests(_ResetSetup):
    def test_teacher_author_is_denied_and_sees_no_button(self):
        response = self._post_reset(self.teacher, [self.second.pk])
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self._exists(self.second))
        page = self._client(self.teacher).get(reverse("exams:teacher_exam_results", kwargs={"slug": self.exam.slug}))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "js-reset-attempt")
        self.assertNotContains(page, "resetAttemptsModal")

    def test_exam_center_staff_is_denied(self):
        response = self._post_reset(self.center_staff, [self.second.pk])
        self.assertEqual(response.status_code, 403)
        self.assertTrue(self._exists(self.second))

    def test_exam_center_head_resets_attempt_and_attempts_left_goes_up(self):
        self.assertEqual(self._left(), 0)
        response = self._post_reset(self.center_head, [self.second.pk])
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._exists(self.second))
        self.assertTrue(self._exists(self.first))
        self.assertEqual(self._left(), 1)  # cəhd sıfırlandı — midterm yenidən verilə bilər
        # Jurnalın midterm xanası əvvəlki rəsmi cəhdə qayıdır (purge qaydası).
        row = self._score_row()
        self.assertEqual(row.score, Decimal("10"))
        self.assertEqual(row.exam_source["attempt_id"], self.first.pk)

    def test_rim_head_allowed_and_audit_row_has_actor_reason_scores(self):
        response = self._post_reset(self.rim_head, [self.second.pk])
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self._exists(self.second))
        rows = self._reset_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.user_id, self.rim_head.pk)
        self.assertEqual(row.reason, REASON)
        self.assertEqual(row.resource_id, str(self.second.pk))
        self.assertEqual(row.changes["student_id"], self.student.pk)
        self.assertEqual(row.changes["exam_id"], self.exam.pk)
        self.assertEqual(row.changes["scores_before"]["status"], "submitted")
        before = row.changes["scores_before"]
        self.assertTrue(before["score"] and before["max_score"] and before["percent"], before)

    def test_results_page_shows_controls_and_history_for_head(self):
        self._post_reset(self.center_head, [self.second.pk])
        page = self._client(self.center_head).get(
            reverse("exams:teacher_exam_results", kwargs={"slug": self.exam.slug})
        )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "js-reset-attempt")
        self.assertContains(page, "resetAttemptsModal")
        self.assertContains(page, "data-reset-group-card")
        self.assertContains(page, REASON)  # tarixçə: səbəb
        self.assertContains(page, f"#{self.second.pk}")
        self.assertContains(page, "teacher_exam_results_reset.js")
        self.assertNotContains(page, "<script>")  # inline JS yoxdur


class AttemptResetRulesTests(_ResetSetup):
    def test_reason_is_required(self):
        for reason in ("", "   ", "qısa"):
            response = self._post_reset(self.center_head, [self.second.pk], reason=reason)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(self._exists(self.second), reason)
        self.assertEqual(self._reset_rows(), [])
        with self.assertRaises(attempt_reset.ResetReasonError):
            attempt_reset.reset_attempt(self.second, actor=self.center_head, reason="qısa")

    def test_midterm_cell_cleared_when_last_attempt_reset(self):
        self._post_reset(self.center_head, [self.second.pk, self.first.pk])
        self.assertFalse(self._exists(self.first))
        self.assertFalse(self._exists(self.second))
        self.assertIsNone(self._score_row())
        self.assertEqual(self._left(), 2)
        self.assertEqual(len(self._reset_rows()), 2)

    def test_locked_journal_refuses_and_keeps_attempt(self):
        with bypass_rls():
            AssessmentScheme.objects.filter(offering=self.offering).update(
                is_published=True, approval_status="approved"
            )
        result = attempt_reset.reset_attempt(self.second, actor=self.center_head, reason=REASON)
        self.assertEqual(result.status, attempt_reset.STATUS_REFUSED)
        self.assertEqual(result.blockers, ("journal_locked",))
        self.assertTrue(self._exists(self.second))
        self.assertEqual(self._reset_rows(), [])

    def test_other_tenant_or_missing_attempt_is_ignored(self):
        response = self._post_reset(self.center_head, [999999999])
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self._exists(self.second))


class GroupResetTests(_ResetSetup):
    def _group_value(self):
        return unit_filter_value(self.group.pk)

    def _lock_journal(self):
        # Yalnız İKİNCİ cəhd midterm xanasını yazıb → jurnal kilidi yalnız onu bloklayır; birinci sıfırlanır.
        with bypass_rls():
            AssessmentScheme.objects.filter(offering=self.offering).update(
                is_published=True, approval_status="approved"
            )

    def test_preview_counts_and_blockers(self):
        self._lock_journal()
        response = self._client(self.center_head).get(
            reverse("exams:reset_group_preview", kwargs={"slug": self.exam.slug}), {"group": self._group_value()}
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["group"], self.group.name)
        self.assertEqual(data["attempts"], 2)
        self.assertEqual(data["students"], 1)
        self.assertEqual(data["resettable"], 1)
        self.assertEqual(data["blocked"], 1)
        self.assertEqual([item["code"] for item in data["blocker_list"]], ["journal_locked"])
        self.assertTrue(self._exists(self.first) and self._exists(self.second))  # ön baxış yazmır

    def test_preview_denied_for_teacher_and_unknown_group(self):
        url = reverse("exams:reset_group_preview", kwargs={"slug": self.exam.slug})
        self.assertEqual(self._client(self.teacher).get(url, {"group": self._group_value()}).status_code, 403)
        self.assertEqual(self._client(self.center_head).get(url, {"group": "unit:bogus"}).status_code, 400)

    def test_group_reset_partial_refusal_does_not_abort_others(self):
        self._lock_journal()
        with self.captureOnCommitCallbacks(execute=True):
            response = self._client(self.rim_head).post(
                reverse("exams:reset_group_attempts", kwargs={"slug": self.exam.slug}),
                {"group": self._group_value(), "reason": REASON},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._exists(self.first))  # sıfırlandı
        self.assertTrue(self._exists(self.second))  # jurnal kilidi — qaldı
        texts = [str(message) for message in response.context["messages"]]
        self.assertTrue(any(text.startswith("1 ") for text in texts), texts)
        self.assertEqual(len(self._reset_rows()), 1)

    def test_group_reset_requires_reason(self):
        response = self._client(self.center_head).post(
            reverse("exams:reset_group_attempts", kwargs={"slug": self.exam.slug}),
            {"group": self._group_value(), "reason": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self._exists(self.first) and self._exists(self.second))


class CenterTicketResetTests(_ReopenBase):
    """Zal (imtahan mərkəzi) imtahanı: sıfırlamadan sonra bilet ``ASSIGNED`` + yeni PIN, tələbə yenidən başlayır."""

    def test_reset_reopens_ticket_and_student_can_start_again(self):
        self.exam.max_attempts_per_user = 1
        self.exam.save(update_fields=["max_attempts_per_user"])
        attempt = self._finish_attempt()
        self.assertEqual(self.exam.attempts_left_for(self.student), 0)
        old_pin_hash = self.ticket.pin_hash

        with self.captureOnCommitCallbacks(execute=True):
            result = attempt_reset.reset_attempt(attempt, actor=self.center, reason=REASON)
        self.assertTrue(result.ok)
        self.assertEqual(result.tickets_reset, (self.ticket.pk,))
        self.assertFalse(ExamAttempt.objects.filter(pk=attempt.pk).exists())
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_ASSIGNED)
        self.assertIsNone(self.ticket.attempt_id)
        self.assertEqual(self.ticket.language, "")
        self.assertIsNone(self.ticket.completed_at)
        self.assertNotEqual(self.ticket.pin_hash, old_pin_hash)
        self.assertEqual(self.exam.attempts_left_for(self.student), 1)
        self.assertTrue(
            AuditLog.objects.filter(
                resource_type="final_exam_ticket",
                resource_id=str(self.ticket.pk),
                reason="final_ticket_reset_after_attempt_purge",
            ).exists()
        )

        enter_waiting(self.ticket, language="")
        self.ticket.refresh_from_db()
        new_attempt = begin_attempt_for_ticket(self.ticket)
        self.assertNotEqual(new_attempt.pk, attempt.pk)
        self.assertEqual(FinalExamTicket.objects.get(pk=self.ticket.pk).status, TICKET_STATUS_ACTIVE)

    def test_center_head_view_resets_center_exam(self):
        attempt = self._finish_attempt()
        with self.captureOnCommitCallbacks(execute=True):
            response = self._client_for(self.center).post(
                reverse("exams:reset_exam_attempts", kwargs={"slug": self.exam.slug}),
                {"attempt_id": str(attempt.pk), "reason": REASON},
            )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ExamAttempt.objects.filter(pk=attempt.pk).exists())
        self.assertEqual(FinalExamTicket.objects.get(pk=self.ticket.pk).status, TICKET_STATUS_ASSIGNED)

    def test_teacher_cannot_reset_center_exam(self):
        attempt = self._finish_attempt()
        response = self._client_for(self.teacher).post(
            reverse("exams:reset_exam_attempts", kwargs={"slug": self.exam.slug}),
            {"attempt_id": str(attempt.pk), "reason": REASON},
        )
        self.assertIn(response.status_code, (403, 404))
        self.assertTrue(ExamAttempt.objects.filter(pk=attempt.pk).exists())
