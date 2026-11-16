"""Sahib 2026-11-17: canlı imtahanda BİR tələbəyə əlavə vaxt.

«Monitorda tələbənin üzərinə klik edib ona əlavə N dəqiqə vermək olsun — yalnız onun vaxtı uzansın;
bunu edərkən heç nə pozulmasın» (taymer, avtomatik təhvil, digər tələbələr).

Yoxlanılır: deadline riyaziyyatı (müddət, ``end_datetime`` kəsimi, müddətsiz imtahan), xidmətin hədləri və
imtinaları, avtomatik təhvil (sweep) uzadılmış cəhdi köhnə vaxtda BAĞLAMIR, yeni vaxtda BAĞLAYIR, digər
tələbəyə toxunulmur, icazələr (mərkəz / növbətçi nəzarətçi / kənar müəllim / tələbə), snapshot düyməsi, tələbənin
status sorğusu və audit.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.exams.domain.attempt_deadline import attempt_deadline_at, write_window_closed
from apps.exams.models import Exam, ExamAttempt
from apps.exams.services.attempt_time_extension import (
    MAX_TOTAL_MINUTES,
    TimeExtensionError,
    extend_attempt_time,
)
from apps.exams.services.attempts import sweep_overdue_attempts
from apps.exams.services.final_center import begin_attempt_for_ticket, enter_waiting, start_room

from .test_final_center_flow import _FlowBase


def _attempt(*, started, duration=60, end=None, extra=0, room_id=None, trial=False):
    exam = SimpleNamespace(total_duration_minutes=duration, end_datetime=end)
    return SimpleNamespace(
        started_at=started,
        exam=exam,
        extra_time_seconds=extra,
        room_id=room_id,
        is_trial=trial,
        deadline_at=None,
    )


class DeadlineMathTests(SimpleTestCase):
    def test_extra_time_is_added_to_duration_deadline(self):
        start = timezone.now()
        self.assertEqual(attempt_deadline_at(_attempt(started=start)), start + timedelta(minutes=60))
        self.assertEqual(attempt_deadline_at(_attempt(started=start, extra=600)), start + timedelta(minutes=70))

    def test_extra_time_extends_past_the_window_end(self):
        """Pəncərə sonu (end_datetime) deadline-ı kəsir; əlavə vaxt kəsilmiş deadline-ın ÜSTÜNƏ gəlir."""
        start = timezone.now()
        end = start + timedelta(minutes=30)
        self.assertEqual(attempt_deadline_at(_attempt(started=start, end=end)), end)
        self.assertEqual(attempt_deadline_at(_attempt(started=start, end=end, extra=300)), end + timedelta(minutes=5))

    def test_hall_attempt_ignores_window_end_but_keeps_extra(self):
        start = timezone.now()
        end = start + timedelta(minutes=10)
        deadline = attempt_deadline_at(_attempt(started=start, end=end, extra=120, room_id=7))
        self.assertEqual(deadline, start + timedelta(minutes=62))

    def test_untimed_exam_has_no_deadline_and_window_end_moves_with_extra(self):
        start = timezone.now() - timedelta(minutes=20)
        end = timezone.now() - timedelta(minutes=1)
        plain = _attempt(started=start, duration=None, end=end)
        self.assertIsNone(attempt_deadline_at(plain))
        self.assertTrue(write_window_closed(plain, at_time=timezone.now()))
        extended = _attempt(started=start, duration=None, end=end, extra=300)
        self.assertFalse(write_window_closed(extended, at_time=timezone.now()))

    def test_missing_or_zero_extra_changes_nothing(self):
        start = timezone.now()
        bare = SimpleNamespace(started_at=start, exam=SimpleNamespace(total_duration_minutes=45, end_datetime=None))
        self.assertEqual(attempt_deadline_at(bare), start + timedelta(minutes=45))


class _LiveAttemptBase(_FlowBase):
    def _live_attempt(self, ticket=None):
        ticket = ticket or self.ticket
        enter_waiting(ticket, language="")
        if self.session.state != "active":
            start_room(self.session, self.invigilator)
            self.session.refresh_from_db()
        return begin_attempt_for_ticket(ticket)

    def _age(self, attempt, minutes):
        """Cəhdi «minutes dəqiqə əvvəl başlamış» et (imtahan müddəti 60 dəq)."""
        ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(minutes=minutes))
        attempt.refresh_from_db()
        return attempt


class ExtendServiceTests(_LiveAttemptBase):
    def test_extension_moves_only_this_attempts_deadline_and_is_audited(self):
        attempt = self._live_attempt()
        before = attempt.deadline_at
        state = extend_attempt_time(attempt, self.invigilator, minutes=7, reason="Kompüter dondu")
        attempt.refresh_from_db()
        self.assertEqual(attempt.extra_time_seconds, 420)
        self.assertEqual(attempt.deadline_at, before + timedelta(minutes=7))
        self.assertEqual(state["added_minutes"], 7)
        self.assertEqual(state["extra_minutes"], 7)
        log = AuditLog.objects.filter(
            resource_id=str(attempt.pk), reason__startswith="exam_attempt_time_extended"
        ).get()
        self.assertIn("+7m", log.reason)
        self.assertIn("Kompüter dondu", log.reason)
        self.assertEqual(log.user_id, self.invigilator.pk)

        # İkinci əlavə cəmə gəlir.
        extend_attempt_time(attempt, self.center, minutes="3", reason="Yenə dondu")
        attempt.refresh_from_db()
        self.assertEqual(attempt.extra_time_seconds, 600)

    def test_limits_and_required_reason(self):
        attempt = self._live_attempt()
        for minutes in (0, -5, 61, "abc", None):
            with self.assertRaises(TimeExtensionError):
                extend_attempt_time(attempt, self.center, minutes=minutes, reason="x")
        with self.assertRaises(TimeExtensionError):
            extend_attempt_time(attempt, self.center, minutes=5, reason="   ")
        extend_attempt_time(attempt, self.center, minutes=60, reason="a")
        extend_attempt_time(attempt, self.center, minutes=60, reason="b")
        with self.assertRaises(TimeExtensionError):
            extend_attempt_time(attempt, self.center, minutes=1, reason="c")  # cəmi 120 dəq-dən çox olmaz
        attempt.refresh_from_db()
        self.assertEqual(attempt.extra_time_seconds, MAX_TOTAL_MINUTES * 60)

    def test_finished_or_time_over_attempt_is_refused(self):
        attempt = self._live_attempt()
        attempt.mark_finished(status="submitted")
        with self.assertRaises(TimeExtensionError):
            extend_attempt_time(attempt, self.center, minutes=5, reason="x")

    def test_extension_just_after_deadline_is_refused(self):
        """Deadline keçib, grace hələ bitməyib: brauzer artıq təhvil göndərir — uzatma «uğurlu» görünməməlidir."""
        attempt = self._live_attempt()
        ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(minutes=60, seconds=5))
        attempt.refresh_from_db()
        with self.assertRaises(TimeExtensionError):
            extend_attempt_time(attempt, self.center, minutes=5, reason="gec")
        attempt.refresh_from_db()
        self.assertEqual(attempt.extra_time_seconds, 0)
        self.assertFalse(attempt.is_finished)

    def test_attempt_past_deadline_and_grace_is_not_revived(self):
        attempt = self._age(self._live_attempt(), 62)
        with self.assertRaises(TimeExtensionError):
            extend_attempt_time(attempt, self.center, minutes=5, reason="gec")
        attempt.refresh_from_db()
        self.assertEqual(attempt.extra_time_seconds, 0)

    def test_untimed_exam_is_refused(self):
        Exam.objects.filter(pk=self.exam.pk).update(total_duration_minutes=None)
        try:
            attempt = self._live_attempt()
            with self.assertRaises(TimeExtensionError):
                extend_attempt_time(attempt, self.center, minutes=5, reason="x")
        finally:
            Exam.objects.filter(pk=self.exam.pk).update(total_duration_minutes=60)


class AutoSubmitAfterExtensionTests(_LiveAttemptBase):
    def _second_ticket(self):
        from apps.exams.models import FinalExamTicket

        return FinalExamTicket.objects.create(
            organization=self.org, session=self.session, exam=self.exam, student=self.student2
        )

    def test_sweep_keeps_extended_attempt_open_and_closes_others(self):
        extended = self._live_attempt()
        other = self._live_attempt(self._second_ticket())
        extend_attempt_time(self._age(extended, 55), self.center, minutes=10, reason="Texniki problem")
        self._age(extended, 62)  # əsas 60 dəq + grace keçib, amma +10 dəq hələ var
        self._age(other, 62)

        sweep_overdue_attempts(ExamAttempt.objects.filter(pk__in=[extended.pk, other.pk]))
        extended.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(extended.is_finished, "uzadılmış cəhd köhnə vaxtda bağlanmamalıdır")
        self.assertEqual(other.status, "expired", "digər tələbənin vaxtı dəyişməməlidir")
        self.assertEqual(other.extra_time_seconds, 0)

        # Yeni deadline (60 + 10) + grace keçəndə avtomatik təhvil işləyir; cavablar qorunur, bal hesablanır.
        self._age(extended, 71)
        sweep_overdue_attempts(ExamAttempt.objects.filter(pk=extended.pk))
        extended.refresh_from_db()
        self.assertEqual(extended.status, "expired")
        self.assertIsNotNone(extended.finished_at)
        # Bitmə vaxtı yeni deadline ilə kəsilir (köhnə deadline ilə yox).
        self.assertEqual(extended.finished_at, extended.deadline_at)
        self.assertEqual(extended.duration_seconds, 70 * 60)

    def test_lazy_expiry_respects_extension(self):
        attempt = self._live_attempt()
        extend_attempt_time(self._age(attempt, 50), self.center, minutes=15, reason="x")
        self._age(attempt, 65)
        self.assertFalse(attempt.expire_if_time_limit_reached())
        self.assertFalse(attempt.expire_if_write_window_closed())
        self.assertFalse(attempt.is_finished)


class ExtraTimeEndpointTests(_LiveAttemptBase):
    def _url(self, ticket=None):
        ticket = ticket or self.ticket
        return reverse(
            "exams:exam_center_ticket_extra_time", kwargs={"session_id": self.session.pk, "ticket_id": ticket.pk}
        )

    def test_invigilator_and_center_can_extend(self):
        attempt = self._live_attempt()
        response = self._client_for(self.invigilator).post(self._url(), {"minutes": "5", "reason": "Kompüter dondu"})
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["extra_minutes"], 5)
        self.assertIn("5", data["message"])
        response = self._client_for(self.center).post(self._url(), {"minutes": "2", "reason": "Yenə"})
        self.assertEqual(response.status_code, 200)
        attempt.refresh_from_db()
        self.assertEqual(attempt.extra_time_seconds, 420)

    def test_outsiders_cannot_extend(self):
        attempt = self._live_attempt()
        for user in (self.teacher, self.student):
            response = self._client_for(user).post(self._url(), {"minutes": "5", "reason": "x"})
            self.assertIn(response.status_code, (403, 404), user.username)
        self.assertEqual(self._client_for(self.center).get(self._url()).status_code, 405)
        attempt.refresh_from_db()
        self.assertEqual(attempt.extra_time_seconds, 0)

    def test_bad_input_is_reported(self):
        self._live_attempt()
        response = self._client_for(self.center).post(self._url(), {"minutes": "500", "reason": "x"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        response = self._client_for(self.center).post(self._url(), {"minutes": "5", "reason": ""})
        self.assertEqual(response.status_code, 400)

    def test_ticket_without_attempt_is_refused(self):
        response = self._client_for(self.center).post(self._url(), {"minutes": "5", "reason": "x"})
        self.assertEqual(response.status_code, 409)

    def test_snapshot_exposes_time_actions(self):
        snap_url = reverse("exams:exam_center_ticket_snapshot", args=[self.session.pk, self.ticket.pk])
        data = self._client_for(self.invigilator).get(snap_url).json()
        self.assertFalse(data["time_actions"]["extend"])  # hələ başlamayıb
        self._live_attempt()
        data = self._client_for(self.invigilator).get(snap_url).json()
        self.assertTrue(data["time_actions"]["extend"])
        self.assertEqual(data["time_actions"]["extra_minutes"], 0)
        self.assertEqual(data["time_actions"]["max_minutes"], 60)

    def test_monitor_row_shows_extra_minutes(self):
        from apps.exams.services.final_center import session_monitor_snapshot

        attempt = self._live_attempt()
        extend_attempt_time(attempt, self.center, minutes=4, reason="x")
        rows = session_monitor_snapshot(self.session)["students"]
        row = next(r for r in rows if r["ticket_id"] == self.ticket.pk)
        self.assertEqual(row["extra_minutes"], 4)


class StudentStatusCarriesExtraTimeTests(TestCase):
    """Tələbənin açıq səhifəsi yeni vaxtı status sorğusu ilə alır (WS qırıq olsa da)."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        from apps.accounts.models import ProfileRole
        from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
        from apps.organizations.models import Organization
        from core.constants import OrganizationType

        User = get_user_model()
        owner = User.objects.create_user("xt_owner", "xt_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="XT Uni", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
        )
        cls.student = User.objects.create_user("xt_student", "xt_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")
        cls.exam = Exam.objects.create(
            title="XT quiz",
            author=owner,
            organization=cls.org,
            exam_type="test",
            is_active=True,
            total_duration_minutes=30,
        )

    def test_status_api_returns_extra_time_total(self):
        from django.test import Client

        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
        ExamAttempt.objects.filter(pk=attempt.pk).update(extra_time_seconds=300)
        client = Client()
        client.force_login(self.student)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("exams:supervision_status_api", args=[attempt.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["extra_time_seconds"], 300)
