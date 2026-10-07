"""Fon işi tutumu 2026-10-07 — periodik cəhd sweep-lərinin qiyməti.

* Resume-pəncərə sweep-i (60 s) əvvəl HƏR kilidli cəhdi dəqiqədə bir ``FOR UPDATE``
  ilə kilidləyib Python-da rədd edirdi (pəncərəsi bitməyən, əl ilə pauza, konfiqi
  söndürülmüş) — indi deadline SQL-də ön-filtrdir, belə cəhdlər namizəd deyil.
* Qlobal sweep vaxt büdcəsi ilə işləyir: büdcə bitəndə dayanır, qalan cəhdləri
  növbəti icra götürür (overlap kilidinin TTL-i keçilmir, beat sweep-ləri üst-üstə
  yığılmır).
* Vaxtı bitmiş cəhdin müəllim bildirişi müəllifi ``select_related`` ilə alır.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.exams.models import Exam, ExamAttempt, ExamSupervisionConfig
from apps.exams.services.attempts import sweep_overdue_attempts
from apps.exams.services.supervision import sweep_expired_resume_windows
from apps.organizations.models import Organization
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()

LOCMEM_CACHE = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "bg-cap-2026-10-07"}
}


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.teacher = User.objects.create_user("bgcap_t", "bgcap_t@example.com", "StrongPass123!")
        cls.students = [
            User.objects.create_user(f"bgcap_s{i}", f"bgcap_s{i}@example.com", "StrongPass123!") for i in range(3)
        ]
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="BG Cap Org", org_type=OrganizationType.SCHOOL, owner=cls.teacher, status="active", is_active=True
            )
            cls.exam = Exam.objects.create(
                title="BG Cap Exam", author=cls.teacher, is_active=True, total_duration_minutes=60, organization=cls.org
            )

    def setUp(self):
        cache.clear()


@override_settings(CACHES=LOCMEM_CACHE)
class ResumeWindowSweepPrefilterTests(_Base):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.exam.total_duration_minutes = 600
            self.exam.save(update_fields=["total_duration_minutes"])
            self.config = ExamSupervisionConfig.objects.create(
                exam=self.exam, enabled=True, recovery_policy="teacher_controlled", resume_window_seconds=600
            )

    def _locked(self, student, *, minutes_ago, manual=False):
        with bypass_rls():
            attempt = ExamAttempt.objects.create(
                user=student,
                exam=self.exam,
                attempt_number=1,
                status="in_progress",
                supervision_status="locked",
                supervision_manual_lock=manual,
            )
            ExamAttempt.objects.filter(pk=attempt.pk).update(
                supervision_locked_at=timezone.now() - timedelta(minutes=minutes_ago)
            )
        return attempt

    def _sweep_queries(self):
        with bypass_rls(), CaptureQueriesContext(connection) as ctx:
            result = sweep_expired_resume_windows()
        return result, [q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"]]

    def test_attempt_inside_window_is_not_row_locked(self):
        self._locked(self.students[0], minutes_ago=3)
        self._locked(self.students[1], minutes_ago=20, manual=True)

        result, locking = self._sweep_queries()

        self.assertEqual(result, 0)
        self.assertEqual(locking, [], "pəncərəsi bitməyən / əl ilə pauza cəhdi kilidlənməməlidir")

    def test_disabled_config_or_zero_window_is_not_a_candidate(self):
        self._locked(self.students[0], minutes_ago=20)
        with bypass_rls():
            ExamSupervisionConfig.objects.filter(pk=self.config.pk).update(enabled=False)
        self.assertEqual(self._sweep_queries(), (0, []))
        with bypass_rls():
            ExamSupervisionConfig.objects.filter(pk=self.config.pk).update(enabled=True, resume_window_seconds=0)
        self.assertEqual(self._sweep_queries(), (0, []))

    def test_due_attempt_is_still_finished(self):
        due = self._locked(self.students[0], minutes_ago=11)
        waiting = self._locked(self.students[1], minutes_ago=5)

        result, locking = self._sweep_queries()

        self.assertEqual(result, 1)
        self.assertEqual(len(locking), 1)
        with bypass_rls():
            due.refresh_from_db()
            waiting.refresh_from_db()
        self.assertEqual((due.status, due.supervision_status), ("submitted", "removed"))
        self.assertEqual((waiting.status, waiting.supervision_status), ("in_progress", "locked"))


@override_settings(CACHES=LOCMEM_CACHE)
class GlobalSweepTimeBudgetTests(_Base):
    def _overdue(self, student):
        with bypass_rls():
            attempt = ExamAttempt.objects.create(user=student, exam=self.exam, status="in_progress")
            ExamAttempt.objects.filter(pk=attempt.pk).update(started_at=timezone.now() - timedelta(minutes=70))
        return attempt

    def test_exhausted_budget_leaves_the_rest_to_the_next_run(self):
        attempts = [self._overdue(student) for student in self.students]

        with override_settings(EXAM_SWEEP_TIME_BUDGET_SECONDS=0), bypass_rls():
            # Büdcə 0: hər icra irəliləyiş üçün yalnız BİR cəhd bağlayır, qalanı növbəti icraya.
            self.assertEqual(sweep_overdue_attempts(), 1)
            self.assertEqual(ExamAttempt.objects.filter(status="in_progress").count(), 2)
            self.assertEqual(sweep_overdue_attempts(), 1)
            self.assertEqual(sweep_overdue_attempts(), 1)
            self.assertEqual(sweep_overdue_attempts(), 0)
            statuses = set(ExamAttempt.objects.filter(pk__in=[a.pk for a in attempts]).values_list("status", flat=True))
        self.assertEqual(statuses, {"expired"})

    def test_oldest_attempt_is_processed_first(self):
        first, second = self._overdue(self.students[0]), self._overdue(self.students[1])

        with override_settings(EXAM_SWEEP_TIME_BUDGET_SECONDS=0), bypass_rls():
            self.assertEqual(sweep_overdue_attempts(), 1)
            first.refresh_from_db()
            second.refresh_from_db()
        self.assertEqual((first.status, second.status), ("expired", "in_progress"))

    def test_default_budget_finishes_everything_in_one_run(self):
        for student in self.students:
            self._overdue(student)
        with bypass_rls():
            self.assertEqual(sweep_overdue_attempts(), 3)

    def test_scoped_call_has_no_budget(self):
        for student in self.students:
            self._overdue(student)
        with override_settings(EXAM_SWEEP_TIME_BUDGET_SECONDS=0), bypass_rls():
            self.assertEqual(sweep_overdue_attempts(ExamAttempt.objects.filter(exam=self.exam)), 3)

    def test_teacher_notification_does_not_refetch_the_author_per_attempt(self):
        for student in self.students:
            self._overdue(student)

        with bypass_rls(), CaptureQueriesContext(connection) as ctx:
            self.assertEqual(sweep_overdue_attempts(), 3)

        author_lookups = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].startswith('SELECT "auth_user"') and f'"auth_user"."id" = {self.teacher.pk}' in q["sql"]
        ]
        self.assertEqual(author_lookups, [])


class FinalReminderBatchingTests(TestCase):
    """Final xatırlatmaları hissə-hissə: sorğu sayı bilet sayından asılı deyil; xəta mərhələni yazmır."""

    @classmethod
    def setUpTestData(cls):
        cls.center = User.objects.create_user("bgcap_center", "bgcap_center@example.com", "StrongPass123!")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="BG Cap Uni",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.center,
                status="active",
                is_active=True,
            )
            cls.exam = Exam.objects.create(
                title="BG Cap Final",
                author=cls.center,
                organization=cls.org,
                exam_type="test",
                exam_type_extended="final",
                is_active=True,
                total_duration_minutes=60,
                start_datetime=timezone.now() + timedelta(days=2),
                end_datetime=timezone.now() + timedelta(days=2, hours=2),
            )

    def _tickets(self, count, prefix):
        from apps.exams.models import FinalExamTicket

        students = [
            User.objects.create_user(f"{prefix}{i}", f"{prefix}{i}@example.com", "StrongPass123!") for i in range(count)
        ]
        with bypass_rls():
            return [FinalExamTicket.objects.create(organization=self.org, exam=self.exam, student=s) for s in students]

    def _run(self):
        from apps.exams.services.final_center import notify_upcoming_final_exams

        with override_settings(FINAL_EXAM_REMINDER_DAYS=(3, 1)), bypass_rls(), CaptureQueriesContext(connection) as ctx:
            sent = notify_upcoming_final_exams()
        return sent, len(ctx.captured_queries)

    def test_query_count_does_not_grow_with_ticket_count(self):
        from apps.exams.models import FinalExamTicket
        from apps.notifications.models import InAppNotification

        self._tickets(2, "bgcap_a")
        sent_small, queries_small = self._run()
        self._tickets(12, "bgcap_b")
        sent_big, queries_big = self._run()

        self.assertEqual((sent_small, sent_big), (2, 12))
        self.assertEqual(queries_big, queries_small, "xatırlatma sorğu sayı bilet sayına görə artmamalıdır")
        with bypass_rls():
            self.assertEqual(set(FinalExamTicket.objects.values_list("reminder_stage", flat=True)), {3})
            self.assertEqual(InAppNotification.objects.filter(notification_type="exam").count(), 14)
        self.assertEqual(self._run()[0], 0, "eyni mərhələ təkrar göndərilməməlidir")

    def test_failed_chunk_keeps_stage_for_retry(self):
        from unittest.mock import patch

        from apps.exams.models import FinalExamTicket

        self._tickets(3, "bgcap_c")
        with patch("apps.notifications.public.create_notification_for_users", side_effect=RuntimeError("boom")):
            self.assertEqual(self._run()[0], 0)
        with bypass_rls():
            self.assertEqual(set(FinalExamTicket.objects.values_list("reminder_stage", flat=True)), {0})
        self.assertEqual(self._run()[0], 3)


class AnswerIndexHygieneTests(TestCase):
    """exams/0072: cavab cədvəllərinin prefiks-təkrar indeksləri yoxdur, unikal kompozitlər qalır."""

    def _indexes(self, table):
        with connection.cursor() as cursor:
            cursor.execute("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = %s", [table])
            return dict(cursor.fetchall())

    def test_prefix_redundant_answer_indexes_are_gone(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL catalog")
        answer = self._indexes("exams_examanswer")
        options = self._indexes("exams_examanswer_selected_options")
        self.assertNotIn("exams_examanswer_attempt_id_3ba11114", answer)
        self.assertNotIn("exams_examanswer_selected_options_examanswer_id_9bd3bf6c", options)
        # Oxu / CASCADE yolları unikal kompozitlərlə indeksli qalır (prefiks = attempt_id / examanswer_id).
        self.assertTrue(any("UNIQUE" in d and "(attempt_id, question_id)" in d for d in answer.values()))
        self.assertTrue(any("UNIQUE" in d and "(examanswer_id, examquestionoption_id)" in d for d in options.values()))


class OverdueCandidateSearchTests(_Base):
    """İlkin namizəd axtarışı join-siz (2 sorğu) və köhnə SQL filtri ilə eyni çoxluğu verir."""

    def test_two_step_search_matches_the_sql_narrow(self):
        from apps.exams.domain.attempt_deadline import lazy_expiry_cutoff
        from apps.exams.services.attempts import _narrow_overdue_candidates, _overdue_candidate_ids

        now = timezone.now()
        with bypass_rls():
            ended = Exam.objects.create(
                title="Ended",
                author=self.teacher,
                organization=self.org,
                is_active=True,
                total_duration_minutes=600,
                end_datetime=now - timedelta(minutes=30),
            )
            untimed = Exam.objects.create(
                title="Untimed", author=self.teacher, organization=self.org, is_active=True, total_duration_minutes=0
            )
            rows = [
                (self.exam, 70, "in_progress", False),  # vaxtı bitib → namizəd
                (self.exam, 5, "in_progress", False),  # hələ vaxtı var
                (ended, 5, "draft", False),  # imtahanın end_datetime-ı keçib → namizəd
                (untimed, 500, "in_progress", False),  # müddətsiz — bu sweep-in işi deyil
            ]
            trial_owner = User.objects.create_user("bgcap_trial", "bgcap_trial@example.com", "StrongPass123!")
            attempts = []
            for index, (exam, minutes_ago, status, is_trial) in enumerate(rows):
                attempt = ExamAttempt.objects.create(user=self.students[index % 3], exam=exam, status=status)
                ExamAttempt.objects.filter(pk=attempt.pk).update(
                    started_at=now - timedelta(minutes=minutes_ago), is_trial=is_trial
                )
                attempts.append(attempt)
            trial = ExamAttempt.objects.create(user=trial_owner, exam=self.exam, status="in_progress")
            ExamAttempt.objects.filter(pk=trial.pk).update(started_at=now - timedelta(minutes=90), is_trial=True)

            cutoff = lazy_expiry_cutoff()
            with CaptureQueriesContext(connection) as ctx:
                fast = sorted(_overdue_candidate_ids(ExamAttempt.objects.all(), cutoff))
            narrow = sorted(_narrow_overdue_candidates(ExamAttempt.objects.all(), cutoff).values_list("pk", flat=True))

        self.assertEqual(fast, narrow)
        self.assertEqual(fast, sorted([attempts[0].pk, attempts[2].pk]))
        self.assertEqual(len(ctx.captured_queries), 2)
        self.assertNotIn("JOIN", ctx.captured_queries[0]["sql"], "açıq cəhdlər exams_exam join-i olmadan oxunmalıdır")
