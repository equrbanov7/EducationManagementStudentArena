"""Gecəlik sessiya / OTP saxlama süpürgələri (fon işi tutumu 2026-10-07)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import EmailOTP
from apps.accounts.retention import purge_expired_sessions, purge_stale_otps
from apps.accounts.tasks import purge_expired_sessions_task, purge_stale_otps_task


class SessionPurgeTests(TestCase):
    def test_only_expired_sessions_are_removed(self):
        now = timezone.now()
        Session.objects.create(session_key="e" * 40, session_data="", expire_date=now - timedelta(minutes=1))
        Session.objects.create(session_key="f" * 40, session_data="", expire_date=now - timedelta(days=40))
        Session.objects.create(session_key="v" * 40, session_data="", expire_date=now + timedelta(hours=1))

        self.assertEqual(purge_expired_sessions_task(), 2)
        self.assertEqual(list(Session.objects.values_list("session_key", flat=True)), ["v" * 40])

    @override_settings(SESSION_ENGINE="django.contrib.sessions.backends.cache")
    def test_cache_only_engine_is_a_no_op(self):
        Session.objects.create(session_key="e" * 40, session_data="", expire_date=timezone.now() - timedelta(days=1))
        self.assertEqual(purge_expired_sessions(), 0)
        self.assertEqual(Session.objects.count(), 1)


class OtpPurgeTests(TestCase):
    def _otp(self, *, expired_days_ago):
        expires = timezone.now() - timedelta(days=expired_days_ago)
        otp = EmailOTP.objects.create(email="otp@example.com", purpose=EmailOTP.Purpose.LOGIN, expires_at=expires)
        return otp

    def test_old_otps_are_removed_recent_kept(self):
        old = self._otp(expired_days_ago=45)
        recent = self._otp(expired_days_ago=2)
        live = self._otp(expired_days_ago=-1)

        self.assertEqual(purge_stale_otps_task(), 1)

        remaining = set(EmailOTP.objects.values_list("pk", flat=True))
        self.assertEqual(remaining, {recent.pk, live.pk})
        self.assertNotIn(old.pk, remaining)

    @override_settings(ACCOUNTS_OTP_RETENTION_DAYS=0)
    def test_zero_retention_disables_purge(self):
        self._otp(expired_days_ago=400)
        self.assertEqual(purge_stale_otps(), 0)
        self.assertEqual(EmailOTP.objects.count(), 1)


class BeatScheduleTests(TestCase):
    def test_nightly_purges_are_scheduled(self):
        # Test settings beat cədvəlini daşımır — prod/base cədvəli birbaşa yoxlanır.
        from config.settings import base

        tasks = {entry["task"] for entry in base.CELERY_BEAT_SCHEDULE.values()}
        self.assertTrue(
            {"accounts.purge_expired_sessions", "accounts.purge_stale_otps", "notifications.purge_old"} <= tasks
        )

    def test_tasks_are_registered_with_the_celery_app(self):
        from config.celery import app

        app.loader.import_default_modules()
        for name in ("accounts.purge_expired_sessions", "accounts.purge_stale_otps", "notifications.purge_old"):
            self.assertIn(name, app.tasks)
