"""Tests for the purge_notifications retention command (DATABASE-001)."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.notifications.models import InAppNotification

User = get_user_model()


class PurgeNotificationsCommandTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("notif_user", "notif@example.com", "pw")

    def _make(self, *, deleted_at=None, is_read=False, created_days_ago=0):
        note = InAppNotification.objects.create(recipient=self.user, title="t", is_read=is_read, deleted_at=deleted_at)
        if created_days_ago:
            # created_at is auto_now_add; backdate it via UPDATE to test age windows.
            InAppNotification.objects.filter(pk=note.pk).update(
                created_at=timezone.now() - timedelta(days=created_days_ago)
            )
        return note

    def _run(self, *args):
        out = StringIO()
        call_command("purge_notifications", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_deletes_nothing(self):
        self._make(deleted_at=timezone.now() - timedelta(days=60))
        self._run()  # no --commit
        self.assertEqual(InAppNotification.objects.count(), 1)

    def test_commit_purges_only_old_soft_deleted(self):
        old = self._make(deleted_at=timezone.now() - timedelta(days=60))
        recent = self._make(deleted_at=timezone.now() - timedelta(days=5))
        live = self._make(deleted_at=None)

        self._run("--commit")  # default --soft-deleted-days 30

        remaining = set(InAppNotification.objects.values_list("pk", flat=True))
        self.assertNotIn(old.pk, remaining)  # purged (soft-deleted > 30d ago)
        self.assertIn(recent.pk, remaining)  # within grace window
        self.assertIn(live.pk, remaining)  # never soft-deleted

    def test_unread_is_never_purged_even_with_read_days(self):
        unread_old = self._make(is_read=False, created_days_ago=400)
        self._run("--read-days", "365", "--commit")
        self.assertTrue(InAppNotification.objects.filter(pk=unread_old.pk).exists())

    def test_read_days_opt_in_purges_old_read_only(self):
        read_old = self._make(is_read=True, created_days_ago=400)
        read_recent = self._make(is_read=True, created_days_ago=10)
        self._run("--read-days", "365", "--commit")
        self.assertFalse(InAppNotification.objects.filter(pk=read_old.pk).exists())
        self.assertTrue(InAppNotification.objects.filter(pk=read_recent.pk).exists())
