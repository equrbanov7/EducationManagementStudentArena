"""Audit 2026-09-28 (WP A2) — imtahan vaxtı və sweep reqressiya testləri.

* EX28-04 (P2): deadline grace-i 60 s-lik sweep və istənilən GET pozurdu;
* EX28-05 (P2 latent): ``RLS_TRANSACTION_SCOPED=True`` ilə sweep BÜTÜN açıq cəhdlərin
  sətir kilidlərini sona qədər saxlayırdı; bir cəhdin xətası bütün sweep-i dayandırırdı;
* EX28-07 (P3): ``deadline_at`` ``end_datetime``-ı nəzərə almırdı; müddətsiz cəhd heç bağlanmırdı;
* EX28-08 (P3): coding təhvili deadline + grace-dən sonra da qəbul olunurdu.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.db import OperationalError, connection, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

import pytest

from apps.exams.domain.attempt_deadline import submit_grace
from apps.exams.models import CodingSubmission, Exam, ExamAnswer, ExamAttempt
from apps.exams.services.attempts import get_active_attempt_for_user, sweep_overdue_attempts
from apps.exams.tests import test_coding_exam as _coding_tests
from apps.exams.tests.option_token_utils import option_value
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import (
    LOCMEM_CACHE,
    _make_people,
    _make_quiz,
    _student_client,
)
from apps.exams.tests.test_audit_2026_09_13_sweep_race import SweepRaceBase, _in_own_connection
from core.rls import bypass_rls

DURATION = 30


def _shift_start(attempt, *, minutes=DURATION, seconds=0):
    ExamAttempt.objects.filter(pk=attempt.pk).update(
        started_at=timezone.now() - timedelta(minutes=minutes, seconds=seconds)
    )
    attempt.refresh_from_db()


@override_settings(CACHES=LOCMEM_CACHE)
class GraceWindowIsHonouredEverywhereTests(TestCase):
    """EX28-04 — grace daxilində sweep və GET cəhdi bağlamır; son təhvil saxlanır."""

    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("a2grace")
        cls.exam = _make_quiz(cls.org, cls.teacher, n_questions=1, duration=DURATION)
        cls.question = cls.exam.questions.get()
        cls.correct = cls.question.options.get(is_correct=True)

    def setUp(self):
        self.client = _student_client("a2grace_student", self.org)
        self.client.post(reverse("exams:start_exam", kwargs={"slug": self.exam.slug}))
        self.attempt = ExamAttempt.objects.get(exam=self.exam, user=self.student)
        self.take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id})
        self.assertEqual(self.client.get(self.take_url).status_code, 200)

    def _finish(self):
        return self.client.post(
            self.take_url,
            {
                "submit_action": "finish",
                f"q_{self.question.id}": option_value(self.attempt, self.correct),
                f"q_present_{self.question.id}": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def _assert_last_answer_saved(self):
        data = self._finish().json()
        self.assertTrue(data.get("finished"))
        self.assertFalse(data.get("already_finished"), data)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "expired")
        answer = ExamAnswer.objects.get(attempt=self.attempt, question=self.question)
        self.assertEqual(list(answer.selected_options.values_list("id", flat=True)), [self.correct.id])

    def test_sweep_inside_grace_window_leaves_attempt_open(self):
        _shift_start(self.attempt, seconds=3)

        with bypass_rls():
            self.assertEqual(sweep_overdue_attempts(), 0)

        self._assert_last_answer_saved()

    def test_get_from_another_tab_inside_grace_does_not_close_attempt(self):
        _shift_start(self.attempt, seconds=3)

        self.assertEqual(self.client.get(self.take_url).status_code, 200)
        self.client.get(reverse("exams:exam_result", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id}))
        self.assertIsNotNone(get_active_attempt_for_user(self.exam, self.student))

        self._assert_last_answer_saved()

    def test_sweep_closes_attempt_after_grace(self):
        _shift_start(self.attempt, seconds=int(submit_grace().total_seconds()) + 5)

        with bypass_rls():
            self.assertEqual(sweep_overdue_attempts(), 1)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "expired")


class SweepPerAttemptIsolationTests(TestCase):
    """EX28-05 — bir cəhdin xətası digərlərinin bağlanmasını dayandırmır; vaxtı çatmayan namizəd deyil."""

    def setUp(self):
        self.org, self.teacher, self.student = _make_people("a2iso")
        self.exam = Exam.objects.create(
            title="A2 Iso", author=self.teacher, organization=self.org, is_active=True, total_duration_minutes=60
        )

    def _attempt(self, exam, *, overdue):
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam)
        _shift_start(attempt, minutes=65 if overdue else 5)
        return attempt

    def test_failure_on_one_attempt_does_not_abort_the_sweep(self):
        other_exam = Exam.objects.create(
            title="A2 Iso B", author=self.teacher, organization=self.org, is_active=True, total_duration_minutes=60
        )
        first = self._attempt(self.exam, overdue=True)
        second = self._attempt(other_exam, overdue=True)

        original = ExamAttempt.expire_if_time_limit_reached
        calls = []

        def flaky(attempt, **kwargs):
            calls.append(attempt.pk)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return original(attempt, **kwargs)

        with bypass_rls(), patch.object(ExamAttempt, "expire_if_time_limit_reached", flaky):
            with self.assertLogs("apps.exams.services.sweep_guard", level="ERROR"):
                finished = sweep_overdue_attempts()

        self.assertEqual(finished, 1)
        self.assertEqual(len(calls), 2)
        statuses = dict(ExamAttempt.objects.filter(pk__in=[first.pk, second.pk]).values_list("pk", "status"))
        self.assertEqual(statuses[calls[0]], "in_progress", "xəta verən cəhd toxunulmaz qalır")
        self.assertEqual(statuses[calls[1]], "expired", "növbəti cəhd yenə bağlanır")

    def test_not_yet_overdue_attempt_is_not_a_candidate(self):
        fresh = self._attempt(self.exam, overdue=False)
        calls = []
        original = ExamAttempt.expire_if_time_limit_reached

        def spy(attempt, **kwargs):
            calls.append(attempt.pk)
            return original(attempt, **kwargs)

        with bypass_rls(), patch.object(ExamAttempt, "expire_if_time_limit_reached", spy):
            self.assertEqual(sweep_overdue_attempts(), 0)
        self.assertNotIn(fresh.pk, calls)


@pytest.mark.postgres
@override_settings(RLS_TRANSACTION_SCOPED=True)
class SweepDoesNotHoldRowLocksTests(SweepRaceBase):
    """EX28-05 — flaq açıq: sweep emal etdiyi cəhdlərin və vaxtı çatmayan cəhdin kilidini SAXLAMIR."""

    def _probe_locks(self, attempt_ids):
        """Ayrı bağlantıdan ``FOR UPDATE NOWAIT`` — kilidli sətirlərin id-lərini qaytarır."""

        def probe():
            locked = []
            for attempt_id in attempt_ids:
                try:
                    with transaction.atomic():
                        list(ExamAttempt.objects.select_for_update(nowait=True).filter(pk=attempt_id))
                except OperationalError:
                    locked.append(attempt_id)
            return locked

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_in_own_connection(probe)).result(timeout=20)

    def test_processed_and_fresh_attempts_are_unlocked_during_the_sweep(self):
        from apps.exams.tasks import expire_overdue_attempts

        student_b = type(self.student).objects.create_user("sweep_race_s2", "sweep_race_s2@example.com", "x")
        with bypass_rls():
            first = self._overdue_attempt()
            second = ExamAttempt.objects.create(user=student_b, exam=self.exam, status="in_progress")
            ExamAttempt.objects.filter(pk=second.pk).update(started_at=timezone.now() - timedelta(minutes=90))
            fresh_exam = Exam.objects.create(
                title="Fresh", author=self.teacher, is_active=True, total_duration_minutes=60, organization=self.org
            )
            fresh = ExamAttempt.objects.create(user=self.student, exam=fresh_exam, status="in_progress")
        all_ids = [first.pk, second.pk, fresh.pk]

        original = ExamAttempt.expire_if_time_limit_reached
        observed = []
        lock = threading.Lock()

        def probing(attempt, **kwargs):
            others = [pk for pk in all_ids if pk != attempt.pk]
            with lock:
                observed.append((attempt.pk, connection.in_atomic_block, self._probe_locks(others)))
            return original(attempt, **kwargs)

        with patch.object(ExamAttempt, "expire_if_time_limit_reached", probing):
            self.assertEqual(expire_overdue_attempts(), 2)

        self.assertEqual(sorted(pk for pk, _atomic, _locked in observed), sorted([first.pk, second.pk]))
        for attempt_pk, in_atomic, locked in observed:
            self.assertTrue(in_atomic)
            self.assertEqual(locked, [], f"attempt {attempt_pk} emal olunarkən kilidli sətirlər: {locked}")
        with bypass_rls():
            self.assertEqual(
                ExamAttempt.objects.get(pk=fresh.pk).status, "in_progress", "vaxtı çatmayan cəhd bağlanmamalıdır"
            )


class DeadlineRespectsExamWindowTests(TestCase):
    """EX28-07 — deadline = min(start + müddət, end_datetime); zal cəhdi və gec başlayan istisnadır."""

    def setUp(self):
        self.org, self.teacher, self.student = _make_people("a2win")
        self.now = timezone.now()
        self.exam = Exam.objects.create(
            title="A2 Window",
            author=self.teacher,
            organization=self.org,
            is_active=True,
            total_duration_minutes=60,
            end_datetime=self.now + timedelta(minutes=10),
        )

    def _attempt(self, **extra):
        return ExamAttempt(exam=self.exam, user=self.student, started_at=self.now, **extra)

    def test_end_datetime_caps_deadline(self):
        self.assertEqual(self._attempt().deadline_at, self.exam.end_datetime)

    def test_hall_bound_attempt_keeps_full_duration(self):
        self.assertEqual(self._attempt(room_id=1).deadline_at, self.now + timedelta(minutes=60))

    def test_attempt_started_after_end_is_not_cut(self):
        attempt = self._attempt()
        attempt.started_at = self.exam.end_datetime + timedelta(minutes=1)
        self.assertEqual(attempt.deadline_at, attempt.started_at + timedelta(minutes=60))


@override_settings(CACHES=LOCMEM_CACHE)
class NoDurationExamClosesAtEndTests(TestCase):
    """EX28-07 — müddətsiz imtahan: `end_datetime` + grace keçəndən sonra POST yazısı qəbul olunmur."""

    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("a2nodur")
        cls.exam = _make_quiz(cls.org, cls.teacher, n_questions=1, duration=None)
        cls.question = cls.exam.questions.get()
        cls.correct = cls.question.options.get(is_correct=True)

    def test_post_after_end_plus_grace_expires_without_saving(self):
        client = _student_client("a2nodur_student", self.org)
        client.post(reverse("exams:start_exam", kwargs={"slug": self.exam.slug}))
        attempt = ExamAttempt.objects.get(exam=self.exam, user=self.student)
        take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})
        self.assertEqual(client.get(take_url).status_code, 200)
        _shift_start(attempt, minutes=10)
        Exam.objects.filter(pk=self.exam.pk).update(end_datetime=timezone.now() - timedelta(minutes=1))

        response = client.post(
            take_url,
            {
                "submit_action": "autosave",
                f"q_{self.question.id}": option_value(attempt, self.correct),
                f"q_present_{self.question.id}": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertTrue(response.json().get("already_finished"))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "expired")
        answer = ExamAnswer.objects.get(attempt=attempt, question=self.question)
        self.assertFalse(answer.selected_options.exists())


class CodingSubmitAfterDeadlineTests(TestCase):
    """EX28-08 — coding təhvili deadline + grace-dən sonra rədd olunur, grace daxilində qəbul olunur."""

    # Test sinfini import etmirik — pytest onun testlərini burada təkrar toplayardı.
    setUp = _coding_tests.CodingExamSubmissionApiTests.setUp

    PAYLOAD = {
        "selected_language": "python",
        "files": [{"name": "main.py", "content": "print('hello')\n", "language": "python", "is_main": True}],
        "stdin": "",
    }

    def _submit(self, *, overdue_seconds):
        self.exam.total_duration_minutes = DURATION
        self.exam.save(update_fields=["total_duration_minutes"])
        _shift_start(self.attempt, seconds=overdue_seconds)
        return self.client.post(
            reverse("exams:coding_submit", kwargs={"slug": self.exam.slug, "attempt_id": self.attempt.id}),
            data=json.dumps(self.PAYLOAD),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_submit_after_grace_is_rejected(self):
        response = self._submit(overdue_seconds=int(submit_grace().total_seconds()) + 60)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get("finished"))
        self.assertFalse(CodingSubmission.objects.filter(attempt=self.attempt, is_final=True).exists())
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "expired")

    def test_submit_inside_grace_is_accepted_as_expired(self):
        response = self._submit(overdue_seconds=2)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(CodingSubmission.objects.filter(attempt=self.attempt, is_final=True).exists())
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "expired")
