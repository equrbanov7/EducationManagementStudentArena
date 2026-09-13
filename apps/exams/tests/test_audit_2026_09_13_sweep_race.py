"""2026-09-13 infra auditi P2-6 / P3-14 — periodik sweep-lərin yarış və overlap qoruması.

P2-6: ``sweep_overdue_attempts`` / ``sweep_expired_resume_windows`` əvvəl
``.iterator()`` + kor ``mark_finished`` idi. Tələbənin təhvil yolu sətri
``select_for_update(of=("self",))`` ilə tutub ``submitted`` yazır; sweep isə
kilid götürmədiyi üçün UPDATE-i tələbənin commit-inə qədər gözləyib sonra
köhnə obyektlə ``expired`` yazırdı (last-writer-wins) — tələbənin təhvili
itirdi, ``schedule_journal_sync`` iki dəfə işlədi. İndi sweep hər cəhdi
``skip_locked`` ilə yenidən oxuyur: tələbə sətri tutubsa ötürür, buraxandan
sonra status filtri (``submitted`` artıq namizəd deyil) onu kəsir.

P3-14: qlobal sweep 55 s ``cache.add`` kilidi ilə — paralel ikinci icra
heç nə etmədən çıxır; org-skoplu (``queryset`` ötürülən) çağırış kilidə tabe
deyil.

Yalnız PostgreSQL (sətir kilidləri); ``TransactionTestCase`` — hər thread öz
bağlantısı ilə real paralel tranzaksiya açır (model:
``apps/registrar/tests/test_grade_write_concurrency.py``).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

import pytest

from apps.exams.models import Exam, ExamAttempt, ExamSupervisionConfig, SupervisionIncident
from apps.exams.services.attempts import sweep_overdue_attempts
from apps.exams.services.supervision import sweep_expired_resume_windows
from apps.exams.services.sweep_guard import SWEEP_LOCK_KEY_PREFIX
from apps.organizations.models import Organization
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()

LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "sweep-race-test",
    }
}


def _in_own_connection(fn):
    """Thread gövdəsi: öz DB bağlantısı, bypass_rls, sonda bağlantını bağla."""

    def run():
        close_old_connections()
        try:
            with bypass_rls():
                return fn()
        finally:
            close_old_connections()

    return run


@pytest.mark.postgres
class SweepRaceBase(TransactionTestCase):
    DURATION_MINUTES = 60

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row locks required")
        self.teacher = User.objects.create_user("sweep_race_t", "sweep_race_t@example.com", "StrongPass123!")
        self.student = User.objects.create_user("sweep_race_s", "sweep_race_s@example.com", "StrongPass123!")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="Sweep Race Org",
                org_type=OrganizationType.SCHOOL,
                owner=self.teacher,
                status="active",
                is_active=True,
            )
            self.exam = Exam.objects.create(
                title="Sweep Race Exam",
                author=self.teacher,
                is_active=True,
                total_duration_minutes=self.DURATION_MINUTES,
                organization=self.org,
            )

    def _overdue_attempt(self):
        with bypass_rls():
            attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
            ExamAttempt.objects.filter(pk=attempt.pk).update(
                started_at=timezone.now() - timedelta(minutes=self.DURATION_MINUTES + 5)
            )
        return attempt

    def _race_student_submit_against(self, attempt, sweep):
        """Tələbə sətri FOR UPDATE ilə tutub gözləyir; sweep bu arada işə düşür.

        Qaytarır: (sweep nəticəsi, tələbə thread-inin nəticəsi). Köhnə kodda
        sweep UPDATE-i tələbənin kilidində bloklanır → ``result(timeout)``
        TimeoutError atır (test qırmızı); yeni kodda ``skip_locked`` dərhal
        ötürür.
        """
        lock_held = threading.Event()
        release = threading.Event()

        def student_submit():
            with transaction.atomic():
                locked = ExamAttempt.objects.select_for_update(of=("self",)).get(pk=attempt.pk)
                lock_held.set()
                release.wait(timeout=20)
                locked.mark_finished(status="submitted")
            return "submitted"

        def sweeper():
            assert lock_held.wait(timeout=10), "tələbə kilidi vaxtında alınmadı"
            return sweep()

        with ThreadPoolExecutor(max_workers=2) as pool:
            student_future = pool.submit(_in_own_connection(student_submit))
            sweep_future = pool.submit(_in_own_connection(sweeper))
            try:
                sweep_result = sweep_future.result(timeout=15)
            finally:
                release.set()
            student_result = student_future.result(timeout=30)
        return sweep_result, student_result


class SweepOverdueAttemptsRaceTest(SweepRaceBase):
    def test_student_submit_is_never_overwritten_to_expired(self):
        attempt = self._overdue_attempt()

        sweep_result, student_result = self._race_student_submit_against(attempt, sweep_overdue_attempts)

        self.assertEqual(sweep_result, 0, "kilidli sətir skip_locked ilə ötürülməli idi")
        self.assertEqual(student_result, "submitted")
        with bypass_rls():
            attempt.refresh_from_db()
        self.assertEqual(attempt.status, "submitted")

        # Tələbə buraxandan sonra da sweep artıq bitmiş cəhdə toxunmur.
        with bypass_rls():
            self.assertEqual(sweep_overdue_attempts(), 0)
            attempt.refresh_from_db()
        self.assertEqual(attempt.status, "submitted")

    def test_sweep_still_expires_unlocked_overdue_attempts(self):
        """Reqressiya: kilid mexanizmi normal halda bitirməni pozmur."""
        attempt = self._overdue_attempt()
        with bypass_rls():
            self.assertEqual(sweep_overdue_attempts(), 1)
            attempt.refresh_from_db()
        self.assertEqual(attempt.status, "expired")
        self.assertTrue(attempt.is_finished)

    @override_settings(CACHES=LOCMEM_CACHE)
    def test_global_sweep_skips_when_overlap_lock_is_held(self):
        attempt = self._overdue_attempt()
        key = f"{SWEEP_LOCK_KEY_PREFIX}overdue_attempts"
        cache.clear()
        self.assertTrue(cache.add(key, "other-run", 55))
        try:
            with bypass_rls():
                self.assertEqual(sweep_overdue_attempts(), 0)
                attempt.refresh_from_db()
                self.assertEqual(attempt.status, "in_progress")
                # Org-skoplu (lazy monitor) çağırış qlobal kilidə tabe deyil.
                self.assertEqual(sweep_overdue_attempts(ExamAttempt.objects.filter(exam=self.exam)), 1)
                attempt.refresh_from_db()
            self.assertEqual(attempt.status, "expired")
            # Başqa icranın kilidi silinməyib (sahiblik tokeni fərqlidir).
            self.assertEqual(cache.get(key), "other-run")
        finally:
            cache.delete(key)

    @override_settings(CACHES=LOCMEM_CACHE)
    def test_global_sweep_releases_its_own_lock(self):
        attempt = self._overdue_attempt()
        key = f"{SWEEP_LOCK_KEY_PREFIX}overdue_attempts"
        cache.clear()
        with bypass_rls():
            self.assertEqual(sweep_overdue_attempts(), 1)
            attempt.refresh_from_db()
        self.assertEqual(attempt.status, "expired")
        self.assertIsNone(cache.get(key), "sweep öz kilidini buraxmalıdır")


class SweepExpiredResumeWindowsRaceTest(SweepRaceBase):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.exam.total_duration_minutes = 600  # vaxt limiti yox — yalnız resume pəncərəsi
            self.exam.save(update_fields=["total_duration_minutes"])
            ExamSupervisionConfig.objects.create(
                exam=self.exam,
                enabled=True,
                recovery_policy="teacher_controlled",
                resume_window_seconds=600,
            )

    def _stale_locked_attempt(self):
        with bypass_rls():
            attempt = ExamAttempt.objects.create(
                user=self.student,
                exam=self.exam,
                attempt_number=1,
                status="in_progress",
                supervision_status="locked",
            )
            attempt.supervision_locked_at = timezone.now() - timedelta(minutes=20)
            attempt.save(update_fields=["supervision_locked_at"])
        return attempt

    def test_student_submit_is_not_overwritten_and_no_duplicate_incident(self):
        attempt = self._stale_locked_attempt()

        sweep_result, student_result = self._race_student_submit_against(attempt, sweep_expired_resume_windows)

        self.assertEqual(sweep_result, 0)
        self.assertEqual(student_result, "submitted")
        with bypass_rls():
            attempt.refresh_from_db()
            self.assertEqual(attempt.status, "submitted")
            # Sweep toxunmadığı üçün nə `removed` yazılıb, nə də insident yaranıb.
            self.assertEqual(attempt.supervision_status, "locked")
            self.assertEqual(
                SupervisionIncident.objects.filter(attempt=attempt, event_type="resume_window_expired").count(), 0
            )
            self.assertEqual(sweep_expired_resume_windows(), 0)

    def test_sweep_still_finishes_stale_locked_attempt(self):
        attempt = self._stale_locked_attempt()
        with bypass_rls():
            self.assertEqual(sweep_expired_resume_windows(), 1)
            attempt.refresh_from_db()
            self.assertTrue(attempt.is_finished)
            self.assertEqual(attempt.supervision_status, "removed")
            self.assertEqual(
                SupervisionIncident.objects.filter(attempt=attempt, event_type="resume_window_expired").count(), 1
            )

    @override_settings(CACHES=LOCMEM_CACHE)
    def test_global_resume_sweep_respects_overlap_lock(self):
        attempt = self._stale_locked_attempt()
        key = f"{SWEEP_LOCK_KEY_PREFIX}expired_resume_windows"
        cache.clear()
        self.assertTrue(cache.add(key, "other-run", 55))
        try:
            with bypass_rls():
                self.assertEqual(sweep_expired_resume_windows(), 0)
                attempt.refresh_from_db()
            self.assertEqual(attempt.status, "in_progress")
        finally:
            cache.delete(key)
