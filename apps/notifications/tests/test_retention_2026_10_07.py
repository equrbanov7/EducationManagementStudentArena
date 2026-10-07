"""Gecəlik bildiriş saxlama süpürgəsi ``notifications.purge_old`` (fon işi tutumu 2026-10-07)."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.notifications.models import InAppNotification
from apps.notifications.tasks import purge_old_notifications_task

User = get_user_model()


class PurgeOldNotificationsTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("notif_ret", "notif_ret@example.com", "pw")

    def _make(self, *, deleted_days_ago=None, is_read=False, created_days_ago=0):
        now = timezone.now()
        note = InAppNotification.objects.create(
            recipient=self.user,
            title="t",
            is_read=is_read,
            deleted_at=now - timedelta(days=deleted_days_ago) if deleted_days_ago is not None else None,
        )
        if created_days_ago:
            InAppNotification.objects.filter(pk=note.pk).update(created_at=now - timedelta(days=created_days_ago))
        return note

    def test_default_purges_only_old_soft_deleted(self):
        old = self._make(deleted_days_ago=60)
        recent = self._make(deleted_days_ago=5)
        old_read = self._make(is_read=True, created_days_ago=800)
        old_unread = self._make(created_days_ago=800)

        self.assertEqual(purge_old_notifications_task(), {"soft_deleted": 1, "read": 0})

        remaining = set(InAppNotification.objects.values_list("pk", flat=True))
        self.assertEqual(remaining, {recent.pk, old_read.pk, old_unread.pk})
        self.assertNotIn(old.pk, remaining)

    @override_settings(NOTIFICATIONS_READ_RETENTION_DAYS=365)
    def test_read_retention_is_opt_in_and_never_touches_unread(self):
        old_read = self._make(is_read=True, created_days_ago=400)
        new_read = self._make(is_read=True, created_days_ago=10)
        old_unread = self._make(created_days_ago=400)

        self.assertEqual(purge_old_notifications_task(), {"soft_deleted": 0, "read": 1})

        remaining = set(InAppNotification.objects.values_list("pk", flat=True))
        self.assertEqual(remaining, {new_read.pk, old_unread.pk})
        self.assertNotIn(old_read.pk, remaining)

    @override_settings(NOTIFICATIONS_SOFT_DELETED_RETENTION_DAYS=0)
    def test_zero_soft_deleted_retention_disables(self):
        self._make(deleted_days_ago=400)
        self.assertEqual(purge_old_notifications_task(), {"soft_deleted": 0, "read": 0})
        self.assertEqual(InAppNotification.objects.count(), 1)
