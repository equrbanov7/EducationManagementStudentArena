"""
Characterization tests for the ``notifications/services.py`` refactor (P1.4).

These tests pin the CURRENT behavior of the notification service layer before
``services.py`` is split into a ``services/`` package. They cover the public
API surface directly (create / read / unread / delete / query helpers) and the
re-export contract, so the refactor cannot silently drop a name or change a
function's behavior.

The ``notify_*`` event flows are already covered end-to-end by
``test_notification_events.py``; this file focuses on the service primitives
and the package's public API.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.notifications import services
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


# Every name that external callers import from apps.notifications.services.
# Captured from the pre-refactor module; the refactored package's __init__
# must continue to expose all of them.
EXPECTED_PUBLIC_API = {
    "build_profile_notification_state",
    "bulk_delete_notifications",
    "create_notification",
    "create_notification_for_users",
    "delete_notification",
    "get_exam_assigned_user_ids",
    "get_lab_assigned_user_ids",
    "get_unread_count",
    "get_user_notifications",
    "mark_all_notifications_read",
    "mark_notification_read",
    "mark_notification_unread",
    "notify_course_membership_assigned",
    "notify_group_assignment",
    "notify_member_removed_from_organization",
    "notify_membership_request_resolution",
    "notify_org_admins_of_new_request",
    "notify_org_owner_pending_approval",
    "notify_student_about_feedback",
    "notify_task_assignment",
    "notify_teacher_about_submission",
    "notify_user_invited_to_organization",
}


class NotificationServicePublicApiTest(TestCase):
    """The services package must expose the full pre-refactor public API."""

    def test_all_public_names_importable(self):
        missing = sorted(name for name in EXPECTED_PUBLIC_API if not hasattr(services, name))
        self.assertEqual(
            missing,
            [],
            f"notifications.services is missing public names after refactor: {missing}",
        )

    def test_get_membership_request_role_label_still_available(self):
        # Used internally and historically importable.
        self.assertTrue(hasattr(services, "get_membership_request_role_label"))


class CreateNotificationTest(TestCase):
    """Pin create_notification / create_notification_for_users behavior."""

    def setUp(self):
        self.user = User.objects.create_user(username="notif_user", email="nu@example.com", password="pw12345678")

    def test_create_notification_returns_instance_with_fields(self):
        notif = create_notification(
            recipient=self.user,
            title="Hello",
            message="Body text",
            notification_type=NotificationType.SYSTEM,
        )
        self.assertIsInstance(notif, InAppNotification)
        self.assertEqual(notif.recipient, self.user)
        self.assertEqual(notif.title, "Hello")
        self.assertEqual(notif.message, "Body text")
        self.assertEqual(notif.notification_type, NotificationType.SYSTEM)
        self.assertFalse(notif.is_read)

    def test_create_notification_defaults_to_system_type(self):
        notif = create_notification(recipient=self.user, title="Defaults")
        self.assertEqual(notif.notification_type, NotificationType.SYSTEM)
        self.assertEqual(notif.message, "")
        self.assertEqual(notif.link, "")

    def test_create_notification_serializes_metadata(self):
        notif = create_notification(
            recipient=self.user,
            title="Meta",
            metadata={"task_id": 7, "nested": {"k": "v"}},
        )
        self.assertEqual(notif.metadata["task_id"], 7)
        self.assertEqual(notif.metadata["nested"]["k"], "v")

    def test_create_notification_for_users_bulk_creates(self):
        other = User.objects.create_user(username="notif_user2", email="nu2@example.com", password="pw12345678")
        created = create_notification_for_users(
            recipients=[self.user, other],
            title="Broadcast",
            notification_type=NotificationType.SYSTEM,
        )
        self.assertEqual(len(created), 2)
        self.assertEqual(InAppNotification.objects.filter(title="Broadcast").count(), 2)

    def test_create_notification_for_users_empty_returns_empty_list(self):
        self.assertEqual(create_notification_for_users(recipients=[], title="Nobody"), [])


class ReadUnreadStateTest(TestCase):
    """Pin mark_read / mark_unread / mark_all / get_unread_count behavior."""

    def setUp(self):
        self.user = User.objects.create_user(username="rstate_user", email="rs@example.com", password="pw12345678")
        self.other = User.objects.create_user(username="rstate_other", email="ro@example.com", password="pw12345678")

    def test_mark_notification_read_changes_state(self):
        notif = create_notification(recipient=self.user, title="Unread one")
        changed = mark_notification_read(notification=notif, user=self.user)
        self.assertTrue(changed)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_mark_notification_read_idempotent(self):
        notif = create_notification(recipient=self.user, title="Already read")
        mark_notification_read(notification=notif, user=self.user)
        self.assertFalse(mark_notification_read(notification=notif, user=self.user))

    def test_mark_notification_unread_changes_state(self):
        notif = create_notification(recipient=self.user, title="Toggle")
        mark_notification_read(notification=notif, user=self.user)
        changed = mark_notification_unread(notification=notif, user=self.user)
        self.assertTrue(changed)
        notif.refresh_from_db()
        self.assertFalse(notif.is_read)

    def test_mark_read_rejects_other_users_notification(self):
        notif = create_notification(recipient=self.user, title="Private")
        with self.assertRaises(PermissionError):
            mark_notification_read(notification=notif, user=self.other)

    def test_mark_all_notifications_read_returns_count(self):
        create_notification(recipient=self.user, title="A")
        create_notification(recipient=self.user, title="B")
        create_notification(recipient=self.user, title="C")
        updated = mark_all_notifications_read(user=self.user)
        self.assertEqual(updated, 3)
        self.assertEqual(get_unread_count(user=self.user), 0)

    def test_get_unread_count_excludes_read(self):
        n1 = create_notification(recipient=self.user, title="One")
        create_notification(recipient=self.user, title="Two")
        self.assertEqual(get_unread_count(user=self.user), 2)
        mark_notification_read(notification=n1, user=self.user)
        self.assertEqual(get_unread_count(user=self.user), 1)


class DeleteNotificationTest(TestCase):
    """Pin delete_notification / bulk_delete_notifications behavior."""

    def setUp(self):
        self.user = User.objects.create_user(username="del_user", email="du@example.com", password="pw12345678")
        self.other = User.objects.create_user(username="del_other", email="do@example.com", password="pw12345678")

    def test_delete_notification_soft_deletes(self):
        notif = create_notification(recipient=self.user, title="Delete me")
        delete_notification(notification=notif, user=self.user)
        notif.refresh_from_db()
        self.assertIsNotNone(notif.deleted_at)

    def test_delete_notification_rejects_other_user(self):
        notif = create_notification(recipient=self.user, title="Not yours")
        with self.assertRaises(PermissionError):
            delete_notification(notification=notif, user=self.other)

    def test_bulk_delete_only_affects_own_notifications(self):
        mine_a = create_notification(recipient=self.user, title="Mine A")
        mine_b = create_notification(recipient=self.user, title="Mine B")
        theirs = create_notification(recipient=self.other, title="Theirs")
        deleted = bulk_delete_notifications(
            notification_ids=[mine_a.pk, mine_b.pk, theirs.pk],
            user=self.user,
        )
        self.assertEqual(deleted, 2)
        theirs.refresh_from_db()
        self.assertIsNone(theirs.deleted_at)


class GetUserNotificationsTest(TestCase):
    """Pin get_user_notifications query behavior."""

    def setUp(self):
        self.user = User.objects.create_user(username="query_user", email="qu@example.com", password="pw12345678")

    def test_returns_only_own_non_deleted_notifications(self):
        other = User.objects.create_user(username="query_other", email="qo@example.com", password="pw12345678")
        create_notification(recipient=self.user, title="Mine")
        create_notification(recipient=other, title="Other")
        results = list(get_user_notifications(user=self.user))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Mine")

    def test_filter_by_unread(self):
        read_one = create_notification(recipient=self.user, title="Read one")
        create_notification(recipient=self.user, title="Unread one")
        mark_notification_read(notification=read_one, user=self.user)
        unread = list(get_user_notifications(user=self.user, filter_by="unread"))
        self.assertEqual(len(unread), 1)
        self.assertEqual(unread[0].title, "Unread one")

    def test_search_query_matches_title_and_message(self):
        create_notification(recipient=self.user, title="Binary search task")
        create_notification(recipient=self.user, title="Unrelated", message="something")
        results = list(get_user_notifications(user=self.user, search_query="binary"))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Binary search task")

    def test_excludes_deleted(self):
        notif = create_notification(recipient=self.user, title="Will delete")
        create_notification(recipient=self.user, title="Stays")
        delete_notification(notification=notif, user=self.user)
        results = list(get_user_notifications(user=self.user))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Stays")
