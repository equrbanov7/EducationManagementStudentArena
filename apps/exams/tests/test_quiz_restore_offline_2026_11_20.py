"""Sahib 2026-11-20 (QuizPython577E, nəzarətli quiz): bərpa + internet kəsilməsi.

1. «Quiz keçirəndə mənim blokladığım / dayandırdığım tələbəni bərpa edəndə olmur».
   Prod (28 cəhd): müəllim bir tələbəni «Dayandır» etdi; cəhd pauzada qalarkən 60 s-lik sweep onu deadline-da
   «expired» etdi (``supervision_status`` hələ «locked») — «Bərpa et» artıq «İmtahan bitib» deyirdi.
   Pauza vaxtı da tələbənin vaxtından gedirdi (dialoq «vaxtı qorunur» desə də).
   Kök: əl ilə pauza yalnız view-larda vaxt yoxlamasından azad idi, ``sweep_overdue_attempts`` /
   ``expire_if_time_limit_reached`` onu tanımırdı; bərpa pauza müddətini qaytarmırdı; WS «resumed» xəbəri
   COMMIT-dən əvvəl gedirdi (prod ``ATOMIC_REQUESTS``).
2. Bir alt-tab eyni saniyədə ``window_blurred`` + ``tab_switched`` (+ ikinci blur) kimi 2–3 pozuntu sayılırdı
   (prod: 2 tələbə 1 saniyədə limitə çatıb kilidləndi; biri 10 dəq-lik bərpa pəncərəsi bitib 0 cavabla
   təhvil verildi). Kilid altında da sayılırdı → «əlavə şans» (-1) sayğacı limitin altına endirmirdi.
3. İnternet kəsilməsi pozuntu deyil — brauzer siqnalı (``network_offline``) qəbul olunur, kilidləmir.
JS tərəfi (oflayn rejim, server-avtoritativ kilid) ``tests/js/supervision_network_offline.test.js``-dədir.
"""

from __future__ import annotations

import json
from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.exams.domain.attempt_deadline import MANUAL_PAUSE_MAX_SECONDS, manual_pause_active
from apps.exams.models import ExamAttempt, ProctoringLog, SupervisionIncident
from apps.exams.services.attempts import sweep_overdue_attempts
from apps.exams.services.supervision import log_supervision_incident, teacher_resume_attempt
from apps.exams.tests.test_quiz_proctoring_2026_11_06 import _QuizBase
from apps.exams.tests.test_views import _login_with_org


class _RoomFlowBase(_QuizBase):
    def start_attempt(self, exam):
        _login_with_org(self.client, self.student, self.org)
        self.assertEqual(self.client.get(self.start_url(exam)).status_code, 302)
        return ExamAttempt.objects.get(exam=exam, user=self.student)

    def as_teacher(self):
        _login_with_org(self.client, self.teacher, self.org)

    def as_student(self):
        _login_with_org(self.client, self.student, self.org)

    def pause(self, exam, attempt):
        self.as_teacher()
        url = reverse("exams:exam_supervision_attempt_pause", args=[exam.slug, attempt.pk])
        response = self.client.post(url, {"reason": "Telefon"})
        self.assertEqual(response.status_code, 200, response.content)

    def resume(self, exam, attempt, **data):
        self.as_teacher()
        url = reverse("exams:exam_supervision_attempt_resume", args=[exam.slug, attempt.pk])
        return self.client.post(url, data)

    def shift(self, attempt, *, started_minutes_ago, paused_minutes_ago=None):
        now = timezone.now()
        ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=now - timedelta(minutes=started_minutes_ago))
        if paused_minutes_ago is not None:
            SupervisionIncident.objects.filter(attempt=attempt, teacher_action="teacher_temporary_lock").update(
                timestamp=now - timedelta(minutes=paused_minutes_ago)
            )
        attempt.refresh_from_db()

    def autosave(self, exam, attempt):
        take_url = reverse("exams:take_exam", args=[exam.slug, attempt.pk])
        return self.client.post(take_url, {"submit_action": "autosave"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")


class ManualPauseRestoreTests(_RoomFlowBase):
    """Problem 1: müəllimin «Dayandır»ı → «Bərpa et» — tələbə eyni cəhdə, cavabları və vaxtı ilə qayıdır."""

    def test_paused_attempt_is_not_expired_by_the_sweep_past_its_deadline(self):
        exam = self.make_exam()  # 30 dəq
        attempt = self.start_attempt(exam)
        self.pause(exam, attempt)
        # Tələbə qalan 5 dəqiqə ilə dayandırılıb; indi ilkin deadline 10 dəq əvvəl keçib.
        self.shift(attempt, started_minutes_ago=40, paused_minutes_ago=15)

        self.assertTrue(manual_pause_active(attempt))
        self.assertEqual(sweep_overdue_attempts(ExamAttempt.objects.filter(pk=attempt.pk)), 0)
        self.assertFalse(attempt.expire_if_time_limit_reached())
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "in_progress")
        self.assertEqual(attempt.supervision_status, "locked")

        # Otaq hələ də «Bərpa et» təklif edir (əvvəl: cəhd «Tamamladı», düymə yox).
        self.as_teacher()
        snapshot = self.client.get(reverse("exams:exam_supervision_room_snapshot", args=[exam.slug])).json()
        row = next(row for row in snapshot["rows"] if row["attempt_id"] == attempt.pk)
        self.assertEqual(row["state"], "locked")
        self.assertTrue(row["can_resume"])

    def test_resume_gives_back_the_paused_time_and_student_continues_same_attempt(self):
        exam = self.make_exam()
        attempt = self.start_attempt(exam)
        self.pause(exam, attempt)
        self.shift(attempt, started_minutes_ago=40, paused_minutes_ago=15)

        response = self.resume(exam, attempt)

        self.assertEqual(response.status_code, 200, response.content)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "in_progress")
        self.assertEqual(attempt.supervision_status, "resumed")
        self.assertFalse(attempt.supervision_manual_lock)
        self.assertAlmostEqual(attempt.extra_time_seconds, 15 * 60, delta=5)
        remaining = (attempt.deadline_at - timezone.now()).total_seconds()
        self.assertAlmostEqual(remaining, 5 * 60, delta=10)
        incident = SupervisionIncident.objects.filter(attempt=attempt, event_type="teacher_resumed").get()
        self.assertAlmostEqual(incident.metadata["paused_seconds_credited"], 15 * 60, delta=5)

        # Tələbə yenidən giriş etmədən eyni səhifədən davam edir: status «resumed» → yazı qəbul olunur.
        self.as_student()
        status = self.client.get(reverse("exams:supervision_status_api", args=[attempt.pk])).json()
        self.assertEqual(status["supervision_status"], "resumed")
        self.assertFalse(status["is_finished"])
        self.assertEqual(status["extra_time_seconds"], attempt.extra_time_seconds)
        save = self.autosave(exam, attempt)
        self.assertEqual(save.status_code, 200, save.content)
        self.assertTrue(save.json()["success"])
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "active")
        page = self.client.get(reverse("exams:take_exam", args=[exam.slug, attempt.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertAlmostEqual(page.context["remaining_seconds"], 5 * 60, delta=10)

    def test_short_pause_within_time_is_credited_too(self):
        exam = self.make_exam()
        attempt = self.start_attempt(exam)
        self.pause(exam, attempt)
        self.shift(attempt, started_minutes_ago=10, paused_minutes_ago=4)

        self.assertEqual(self.resume(exam, attempt).status_code, 200)

        attempt.refresh_from_db()
        self.assertAlmostEqual(attempt.extra_time_seconds, 4 * 60, delta=5)
        self.assertAlmostEqual((attempt.deadline_at - timezone.now()).total_seconds(), 24 * 60, delta=10)

    def test_locked_writes_are_refused_until_resume(self):
        exam = self.make_exam()
        attempt = self.start_attempt(exam)
        self.pause(exam, attempt)
        self.as_student()
        self.assertEqual(self.autosave(exam, attempt).status_code, 423)

    def test_forgotten_pause_is_closed_after_the_cap(self):
        exam = self.make_exam()
        attempt = self.start_attempt(exam)
        self.pause(exam, attempt)
        cap_minutes = MANUAL_PAUSE_MAX_SECONDS // 60
        self.shift(attempt, started_minutes_ago=30 + cap_minutes + 5, paused_minutes_ago=cap_minutes + 20)

        self.assertEqual(sweep_overdue_attempts(ExamAttempt.objects.filter(pk=attempt.pk)), 1)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "expired")

    def test_pause_credit_is_capped(self):
        exam = self.make_exam()
        attempt = self.start_attempt(exam)
        self.pause(exam, attempt)
        cap_minutes = MANUAL_PAUSE_MAX_SECONDS // 60
        # Deadline + tavan hələ keçməyib (pauza imtahanın əvvəlində başlayıb), amma pauza tavandan uzundur.
        self.shift(attempt, started_minutes_ago=cap_minutes + 10, paused_minutes_ago=cap_minutes + 9)

        self.assertEqual(self.resume(exam, attempt).status_code, 200)
        attempt.refresh_from_db()
        self.assertEqual(attempt.extra_time_seconds, MANUAL_PAUSE_MAX_SECONDS)

    def test_resume_notifies_student_only_after_commit_with_time_total(self):
        exam = self.make_exam()
        attempt = self.start_attempt(exam)
        self.pause(exam, attempt)
        self.shift(attempt, started_minutes_ago=10, paused_minutes_ago=2)
        attempt.refresh_from_db()

        with mock.patch("apps.exams.services.supervision.actions._notify_student_via_ws") as notify:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                teacher_resume_attempt(attempt, self.teacher)
            notify.assert_not_called()  # tranzaksiya bağlanmamış tələbəyə xəbər getmir
            for callback in callbacks:
                callback()

        payload = notify.call_args.args[1]
        self.assertEqual(payload["action"], "resumed")
        attempt.refresh_from_db()
        self.assertEqual(payload["extra_time_seconds"], attempt.extra_time_seconds)
        self.assertGreater(payload["extra_time_seconds"], 0)

    def test_finished_attempt_is_still_not_revived(self):
        exam = self.make_exam()
        attempt = self.start_attempt(exam)
        self.pause(exam, attempt)
        attempt.refresh_from_db()
        attempt.mark_finished(status="submitted")

        response = self.resume(exam, attempt)

        self.assertEqual(response.status_code, 409)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "submitted")

    @override_settings(EXAM_SUPERVISION_ENABLED=False)
    def test_pause_freeze_follows_the_feature_flag(self):
        exam = self.make_exam()
        attempt = ExamAttempt.objects.create(
            user=self.student,
            exam=exam,
            status="in_progress",
            attempt_number=1,
            supervision_status="locked",
            supervision_manual_lock=True,
        )
        ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(minutes=45))
        attempt.refresh_from_db()
        self.assertFalse(manual_pause_active(attempt))
        self.assertTrue(attempt.expire_if_time_limit_reached())


class ViolationEpisodeTests(_RoomFlowBase):
    """Problem 2: bir hərəkət = bir pozuntu; kilid altında sayılmır; «əlavə şans» həqiqətən şans verir."""

    def log(self, attempt, event_type):
        url = reverse("exams:supervision_log_incident", args=[attempt.pk])
        return self.client.post(
            url, data=json.dumps({"event_type": event_type, "metadata": {}}), content_type="application/json"
        ).json()

    def age_incidents(self, attempt, seconds=10):
        SupervisionIncident.objects.filter(attempt=attempt).update(
            timestamp=timezone.now() - timedelta(seconds=seconds)
        )

    def test_one_alt_tab_counts_once(self):
        exam = self.make_exam()
        attempt = self.start_attempt(exam)

        # Prod-dakı ardıcıllıq: blur + tab_switched + blur — eyni saniyədə.
        first = self.log(attempt, "window_blurred")
        second = self.log(attempt, "tab_switched")
        third = self.log(attempt, "window_blurred")

        self.assertEqual(first["violation_count"], 1)
        self.assertEqual(second["violation_count"], 1)
        self.assertEqual(third["violation_count"], 1)
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_violation_count, 1)
        self.assertEqual(attempt.supervision_status, "active")
        duplicates = SupervisionIncident.objects.filter(attempt=attempt, metadata__counted=False)
        self.assertEqual(duplicates.count(), 2)
        self.assertEqual(set(duplicates.values_list("severity", flat=True)), {"info"})

    def test_separate_episodes_still_reach_the_lock(self):
        exam = self.make_exam()
        attempt = self.start_attempt(exam)
        for _ in range(3):
            self.age_incidents(attempt)
            result = self.log(attempt, "tab_switched")
        self.assertEqual(result["violation_count"], 3)
        self.assertEqual(result["supervision_status"], "locked")
        self.assertEqual(result["action_taken"], "locked")

    def test_events_while_locked_do_not_count_and_extra_chance_gets_below_the_limit(self):
        exam = self.make_exam()
        attempt = self.start_attempt(exam)
        for _ in range(3):
            self.age_incidents(attempt)
            self.log(attempt, "tab_switched")
        for _ in range(2):  # tələbə kilid ekranındadır, pəncərələr arasında keçir
            self.age_incidents(attempt)
            self.log(attempt, "window_blurred")
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_violation_count, 3)

        response = self.resume(exam, attempt, grant_extra_chance="1")

        self.assertEqual(response.status_code, 200, response.content)
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_violation_count, 2)
        self.as_student()
        self.age_incidents(attempt)
        self.assertEqual(self.log(attempt, "fullscreen_restored")["supervision_status"], "resumed")

    def test_extra_chance_clamps_an_overflowed_counter(self):
        exam = self.make_exam()
        attempt = self.locked_attempt(exam)
        ExamAttempt.objects.filter(pk=attempt.pk).update(supervision_violation_count=6, started_at=timezone.now())
        attempt.refresh_from_db()

        teacher_resume_attempt(attempt, self.teacher, grant_extra_chance=True)

        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_violation_count, 2)  # limit 3 → 3 - 1, 6 - 1 deyil

    def test_client_cannot_forge_the_counted_flag(self):
        exam = self.make_exam()
        attempt = self.start_attempt(exam)
        url = reverse("exams:supervision_log_incident", args=[attempt.pk])
        self.client.post(
            url,
            data=json.dumps({"event_type": "tab_switched", "metadata": {"counted": False}}),
            content_type="application/json",
        )
        incident = SupervisionIncident.objects.filter(attempt=attempt, event_type="tab_switched").get()
        self.assertIs(incident.metadata["counted"], True)

    def test_timeline_marks_duplicates_as_not_counting(self):
        from apps.exams.services.supervision.risk import attempt_timeline

        exam = self.make_exam()
        attempt = self.start_attempt(exam)
        log_supervision_incident(attempt, "window_blurred", {})
        log_supervision_incident(attempt, "tab_switched", {})

        rows = {row["code"]: row["counts"] for row in attempt_timeline(attempt) if row["source"] == "rule"}
        self.assertTrue(rows["window_blurred"])
        self.assertFalse(rows["tab_switched"])


class NetworkLossSignalTests(_RoomFlowBase):
    """Problem 3: internet kəsilməsinin izi — siqnal kimi, sayğaca/kilidə təsirsiz."""

    def test_network_offline_signal_is_logged_without_counting(self):
        exam = self.make_exam()
        attempt = self.start_attempt(exam)
        url = reverse("exams:supervision_log_signal", args=[attempt.pk])

        response = self.client.post(
            url,
            data=json.dumps(
                {"kind": "network_offline", "detail": {"seconds": 95, "fs_exit": True, "left_page": False}}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["logged"])
        log = ProctoringLog.objects.get(exam_attempt=attempt)
        self.assertEqual(log.event_type, "network_disconnect")
        self.assertEqual(log.details["kind"], "network_offline")
        self.assertEqual(log.details["severity"], "low")
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_violation_count, 0)
        self.assertEqual(attempt.supervision_status, "active")

    def test_take_page_ships_offline_texts_and_network_module(self):
        exam = self.make_exam()
        attempt = self.start_attempt(exam)
        page = self.client.get(reverse("exams:take_exam", args=[exam.slug, attempt.pk]))
        html = page.content.decode()
        self.assertIn('"offlineTitle"', html)
        self.assertIn('"reconnectMsg"', html)
        self.assertIn("exam_supervision.entry.js", html)
