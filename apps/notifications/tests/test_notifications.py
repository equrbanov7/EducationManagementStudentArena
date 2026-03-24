"""
Tests for the in-app notification system.

Covers:
  - Notification creation (single and bulk)
  - List scoping by user
  - Mark read / unread
  - Mark all as read
  - Soft-delete
  - Unread count accuracy
  - Pagination
  - Security: users cannot access other users' notifications
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.notifications.models import InAppNotification, NotificationType
from apps.notifications.services import (
    bulk_delete_notifications,
    create_notification,
    create_notification_for_users,
    delete_notification,
    get_unread_count,
    get_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    mark_notification_unread,
)

User = get_user_model()


class NotificationModelTest(TestCase):
    """Unit tests for the InAppNotification model."""

    def setUp(self):
        self.user = User.objects.create_user("modeluser", "m@example.com", "TestPass123!")

    def test_default_is_unread(self):
        n = InAppNotification.objects.create(recipient=self.user, title="Hello")
        self.assertFalse(n.is_read)
        self.assertIsNone(n.read_at)

    def test_mark_read(self):
        n = InAppNotification.objects.create(recipient=self.user, title="Hi")
        n.mark_read()
        n.refresh_from_db()
        self.assertTrue(n.is_read)
        self.assertIsNotNone(n.read_at)

    def test_mark_read_idempotent(self):
        n = InAppNotification.objects.create(recipient=self.user, title="Hi", is_read=True)
        old_read_at = timezone.now()
        n.read_at = old_read_at
        n.save()
        n.mark_read()  # should not change anything
        n.refresh_from_db()
        self.assertEqual(n.read_at, old_read_at)

    def test_mark_unread(self):
        n = InAppNotification.objects.create(recipient=self.user, title="Hi", is_read=True)
        n.read_at = timezone.now()
        n.save()
        n.mark_unread()
        n.refresh_from_db()
        self.assertFalse(n.is_read)
        self.assertIsNone(n.read_at)

    def test_soft_delete(self):
        n = InAppNotification.objects.create(recipient=self.user, title="Bye")
        self.assertFalse(n.is_deleted)
        n.soft_delete()
        n.refresh_from_db()
        self.assertTrue(n.is_deleted)
        self.assertIsNotNone(n.deleted_at)

    def test_soft_delete_idempotent(self):
        n = InAppNotification.objects.create(recipient=self.user, title="Bye")
        n.soft_delete()
        first_deleted_at = n.deleted_at
        n.soft_delete()
        self.assertEqual(n.deleted_at, first_deleted_at)

    def test_str(self):
        n = InAppNotification.objects.create(recipient=self.user, title="Test", notification_type="exam")
        self.assertIn("exam", str(n))
        self.assertIn("Test", str(n))


class NotificationCreationServiceTest(TestCase):
    """Tests for notification creation services."""

    def setUp(self):
        self.user1 = User.objects.create_user("user1", "u1@example.com", "TestPass123!")
        self.user2 = User.objects.create_user("user2", "u2@example.com", "TestPass123!")

    def test_create_single_notification(self):
        n = create_notification(
            recipient=self.user1,
            title="Assignment due",
            message="Your assignment is due tomorrow.",
            link="/assignments/1/",
            notification_type=NotificationType.ASSIGNMENT,
        )
        self.assertEqual(n.recipient, self.user1)
        self.assertEqual(n.title, "Assignment due")
        self.assertEqual(n.notification_type, NotificationType.ASSIGNMENT)
        self.assertFalse(n.is_read)

    def test_create_notification_default_type(self):
        n = create_notification(recipient=self.user1, title="System message")
        self.assertEqual(n.notification_type, NotificationType.SYSTEM)

    def test_create_notification_with_metadata(self):
        n = create_notification(
            recipient=self.user1,
            title="New grade",
            metadata={"assignment_id": 42, "score": 95},
        )
        self.assertEqual(n.metadata["assignment_id"], 42)

    def test_create_notification_for_multiple_users(self):
        notifications = create_notification_for_users(
            recipients=[self.user1, self.user2],
            title="Exam starts soon",
            notification_type=NotificationType.EXAM,
        )
        self.assertEqual(len(notifications), 2)
        recipients = {n.recipient_id for n in notifications}
        self.assertIn(self.user1.pk, recipients)
        self.assertIn(self.user2.pk, recipients)

    def test_bulk_create_empty_recipients(self):
        notifications = create_notification_for_users(recipients=[], title="Nobody")
        self.assertEqual(notifications, [])


class NotificationReadUnreadServiceTest(TestCase):
    """Tests for read/unread state management."""

    def setUp(self):
        self.user = User.objects.create_user("readuser", "r@example.com", "TestPass123!")
        self.other = User.objects.create_user("other", "o@example.com", "TestPass123!")

    def _notification(self, **kwargs):
        return create_notification(recipient=self.user, title="T", **kwargs)

    def test_mark_read(self):
        n = self._notification()
        changed = mark_notification_read(notification=n, user=self.user)
        self.assertTrue(changed)
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_mark_read_already_read(self):
        n = self._notification()
        mark_notification_read(notification=n, user=self.user)
        changed = mark_notification_read(notification=n, user=self.user)
        self.assertFalse(changed)

    def test_mark_unread(self):
        n = self._notification()
        mark_notification_read(notification=n, user=self.user)
        changed = mark_notification_unread(notification=n, user=self.user)
        self.assertTrue(changed)
        n.refresh_from_db()
        self.assertFalse(n.is_read)

    def test_mark_read_permission_error(self):
        n = self._notification()
        with self.assertRaises(PermissionError):
            mark_notification_read(notification=n, user=self.other)

    def test_mark_unread_permission_error(self):
        n = self._notification()
        with self.assertRaises(PermissionError):
            mark_notification_unread(notification=n, user=self.other)

    def test_mark_all_read(self):
        for i in range(5):
            create_notification(recipient=self.user, title=f"N{i}")
        count = mark_all_notifications_read(user=self.user)
        self.assertEqual(count, 5)
        still_unread = InAppNotification.objects.filter(recipient=self.user, is_read=False).count()
        self.assertEqual(still_unread, 0)

    def test_mark_all_read_excludes_deleted(self):
        n = create_notification(recipient=self.user, title="To delete")
        n.soft_delete()
        mark_all_notifications_read(user=self.user)
        n.refresh_from_db()
        self.assertFalse(n.is_read)  # deleted notification not affected

    def test_mark_all_read_only_affects_own(self):
        other_n = create_notification(recipient=self.other, title="Other")
        create_notification(recipient=self.user, title="Mine")
        mark_all_notifications_read(user=self.user)
        other_n.refresh_from_db()
        self.assertFalse(other_n.is_read)  # other user's not affected


class NotificationDeleteServiceTest(TestCase):
    """Tests for soft-delete functionality."""

    def setUp(self):
        self.user = User.objects.create_user("deluser", "d@example.com", "TestPass123!")
        self.other = User.objects.create_user("other2", "o2@example.com", "TestPass123!")

    def test_delete_notification(self):
        n = create_notification(recipient=self.user, title="Delete me")
        delete_notification(notification=n, user=self.user)
        n.refresh_from_db()
        self.assertTrue(n.is_deleted)

    def test_delete_permission_error(self):
        n = create_notification(recipient=self.user, title="Mine")
        with self.assertRaises(PermissionError):
            delete_notification(notification=n, user=self.other)

    def test_bulk_delete(self):
        n1 = create_notification(recipient=self.user, title="N1")
        n2 = create_notification(recipient=self.user, title="N2")
        other_n = create_notification(recipient=self.other, title="Other")
        deleted = bulk_delete_notifications(notification_ids=[n1.pk, n2.pk, other_n.pk], user=self.user)
        self.assertEqual(deleted, 2)  # other_n ignored
        n1.refresh_from_db()
        n2.refresh_from_db()
        other_n.refresh_from_db()
        self.assertTrue(n1.is_deleted)
        self.assertTrue(n2.is_deleted)
        self.assertFalse(other_n.is_deleted)


class NotificationQueryServiceTest(TestCase):
    """Tests for get_user_notifications and get_unread_count."""

    def setUp(self):
        self.user = User.objects.create_user("quser", "q@example.com", "TestPass123!")
        self.other = User.objects.create_user("qother", "qo@example.com", "TestPass123!")

    def test_list_scoped_to_user(self):
        create_notification(recipient=self.user, title="Mine")
        create_notification(recipient=self.other, title="Theirs")
        qs = get_user_notifications(user=self.user)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().title, "Mine")

    def test_deleted_excluded_from_list(self):
        n = create_notification(recipient=self.user, title="Gone")
        n.soft_delete()
        qs = get_user_notifications(user=self.user)
        self.assertEqual(qs.count(), 0)

    def test_filter_unread(self):
        n1 = create_notification(recipient=self.user, title="Unread")
        n2 = create_notification(recipient=self.user, title="Read")
        n2.mark_read()
        qs = get_user_notifications(user=self.user, filter_by="unread")
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().pk, n1.pk)

    def test_filter_read(self):
        n1 = create_notification(recipient=self.user, title="Read")
        n1.mark_read()
        create_notification(recipient=self.user, title="Unread")
        qs = get_user_notifications(user=self.user, filter_by="read")
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().pk, n1.pk)

    def test_filter_by_type(self):
        create_notification(recipient=self.user, title="A", notification_type=NotificationType.ASSIGNMENT)
        create_notification(recipient=self.user, title="E", notification_type=NotificationType.EXAM)
        qs = get_user_notifications(user=self.user, notification_type=NotificationType.EXAM)
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().title, "E")

    def test_unread_count(self):
        create_notification(recipient=self.user, title="A")
        n = create_notification(recipient=self.user, title="B")
        n.mark_read()
        self.assertEqual(get_unread_count(user=self.user), 1)

    def test_unread_count_excludes_deleted(self):
        n = create_notification(recipient=self.user, title="Deleted unread")
        n.soft_delete()
        self.assertEqual(get_unread_count(user=self.user), 0)

    def test_unread_count_scoped_to_user(self):
        create_notification(recipient=self.user, title="Mine")
        create_notification(recipient=self.other, title="Theirs")
        self.assertEqual(get_unread_count(user=self.user), 1)


class NotificationViewTest(TestCase):
    """HTTP-level tests for notification views."""

    def setUp(self):
        self.user = User.objects.create_user("viewuser", "v@example.com", "TestPass123!")
        self.other = User.objects.create_user("viewother", "vo@example.com", "TestPass123!")
        self.client.force_login(self.user)

    def _make_notification(self, title="Test", **kwargs):
        return create_notification(recipient=self.user, title=title, **kwargs)

    # ── List ──────────────────────────────────────────────────────────────

    def test_list_view_returns_200(self):
        response = self.client.get(reverse("notifications:notification_list"))
        self.assertEqual(response.status_code, 200)

    def test_list_view_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("notifications:notification_list"))
        self.assertEqual(response.status_code, 302)

    def test_list_shows_own_notifications(self):
        self._make_notification(title="My notif")
        create_notification(recipient=self.other, title="Others")
        response = self.client.get(reverse("notifications:notification_list"))
        self.assertContains(response, "My notif")
        self.assertNotContains(response, "Others")

    def test_list_excludes_deleted(self):
        n = self._make_notification(title="Gone")
        n.soft_delete()
        response = self.client.get(reverse("notifications:notification_list"))
        self.assertNotContains(response, "Gone")

    def test_list_filter_unread(self):
        self._make_notification(title="Unread notif")
        n2 = self._make_notification(title="Read notif")
        n2.mark_read()
        response = self.client.get(reverse("notifications:notification_list") + "?filter=unread")
        self.assertContains(response, "Unread notif")
        self.assertNotContains(response, "Read notif")

    # ── Detail ────────────────────────────────────────────────────────────

    def test_detail_view_returns_200(self):
        n = self._make_notification()
        response = self.client.get(reverse("notifications:notification_detail", args=[n.pk]))
        self.assertEqual(response.status_code, 200)

    def test_detail_marks_as_read(self):
        n = self._make_notification()
        self.assertFalse(n.is_read)
        self.client.get(reverse("notifications:notification_detail", args=[n.pk]))
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_detail_other_user_gets_404(self):
        other_n = create_notification(recipient=self.other, title="Theirs")
        response = self.client.get(reverse("notifications:notification_detail", args=[other_n.pk]))
        self.assertEqual(response.status_code, 404)

    # ── Mark Read / Unread ────────────────────────────────────────────────

    def test_mark_read_post(self):
        n = self._make_notification()
        self.client.post(reverse("notifications:notification_mark_read", args=[n.pk]))
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_mark_unread_post(self):
        n = self._make_notification()
        n.mark_read()
        self.client.post(reverse("notifications:notification_mark_unread", args=[n.pk]))
        n.refresh_from_db()
        self.assertFalse(n.is_read)

    def test_mark_read_other_user_gets_404(self):
        other_n = create_notification(recipient=self.other, title="T")
        response = self.client.post(reverse("notifications:notification_mark_read", args=[other_n.pk]))
        self.assertEqual(response.status_code, 404)

    def test_mark_all_read(self):
        for i in range(3):
            self._make_notification(title=f"N{i}")
        self.client.post(reverse("notifications:notification_mark_all_read"))
        still_unread = InAppNotification.objects.filter(recipient=self.user, is_read=False).count()
        self.assertEqual(still_unread, 0)

    # ── Delete ────────────────────────────────────────────────────────────

    def test_delete_notification(self):
        n = self._make_notification()
        self.client.post(reverse("notifications:notification_delete", args=[n.pk]))
        n.refresh_from_db()
        self.assertTrue(n.is_deleted)

    def test_delete_other_user_notification_gets_404(self):
        other_n = create_notification(recipient=self.other, title="T")
        response = self.client.post(reverse("notifications:notification_delete", args=[other_n.pk]))
        self.assertEqual(response.status_code, 404)

    def test_bulk_delete(self):
        n1 = self._make_notification(title="A")
        n2 = self._make_notification(title="B")
        self.client.post(
            reverse("notifications:notification_bulk_delete"),
            {"ids[]": [n1.pk, n2.pk]},
        )
        n1.refresh_from_db()
        n2.refresh_from_db()
        self.assertTrue(n1.is_deleted)
        self.assertTrue(n2.is_deleted)

    # ── Unread count ──────────────────────────────────────────────────────

    def test_unread_count_endpoint(self):
        self._make_notification()
        response = self.client.get(reverse("notifications:unread_count"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["unread_count"], 1)

    def test_unread_count_updates_after_read(self):
        n = self._make_notification()
        self.client.post(reverse("notifications:notification_mark_read", args=[n.pk]))
        response = self.client.get(reverse("notifications:unread_count"))
        self.assertEqual(response.json()["unread_count"], 0)

    # ── Pagination ────────────────────────────────────────────────────────

    def test_pagination_works(self):
        for i in range(20):
            self._make_notification(title=f"N{i}")
        response = self.client.get(reverse("notifications:notification_list"))
        self.assertEqual(response.status_code, 200)
        # PAGE_SIZE is 15; page 1 should have at most 15 items
        page_obj = response.context["page_obj"]
        self.assertLessEqual(len(page_obj.object_list), 15)

    def test_pagination_page_2(self):
        for i in range(20):
            self._make_notification(title=f"N{i}")
        response = self.client.get(reverse("notifications:notification_list") + "?page=2")
        self.assertEqual(response.status_code, 200)
        page_obj = response.context["page_obj"]
        self.assertEqual(page_obj.number, 2)
