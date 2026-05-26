"""
Read / unread state helpers for in-app notifications.
"""

from django.utils import timezone

from apps.notifications.models import InAppNotification
from core.rls import bypass_rls

from .helpers import _assert_owner


def mark_notification_read(*, notification: InAppNotification, user) -> bool:
    """
    Mark *notification* as read for *user*.

    Returns True if the state changed, False if it was already read.
    Raises PermissionError if *notification* does not belong to *user*.

    The write runs under bypass_rls(): _assert_owner already enforces
    ownership, and the row may belong to an organisation other than the
    currently active one.
    """
    _assert_owner(notification, user)
    if notification.is_read:
        return False
    with bypass_rls():
        notification.mark_read()
    return True


def mark_notification_unread(*, notification: InAppNotification, user) -> bool:
    """
    Mark *notification* as unread for *user*.

    Returns True if the state changed, False if it was already unread.
    Raises PermissionError if *notification* does not belong to *user*.
    """
    _assert_owner(notification, user)
    if not notification.is_read:
        return False
    with bypass_rls():
        notification.mark_unread()
    return True


def mark_all_notifications_read(*, user) -> int:
    """
    Mark all non-deleted, unread notifications for *user* as read.

    Returns the number of notifications updated.

    The ``recipient=user`` filter is the security boundary here, so the call
    runs under ``bypass_rls()``: a user's own inbox must be reachable across
    every organisation they belong to, even before they pick an active org.
    """
    now = timezone.now()
    with bypass_rls():
        updated = InAppNotification.objects.filter(
            recipient=user,
            deleted_at__isnull=True,
            is_read=False,
        ).update(is_read=True, read_at=now)
    return updated


def get_unread_count(*, user) -> int:
    """Return the number of non-deleted unread notifications for *user*.

    Runs under ``bypass_rls()``: the badge count must reflect a user's entire
    inbox regardless of the currently selected organisation. ``recipient=user``
    is the security boundary.
    """
    with bypass_rls():
        return InAppNotification.objects.filter(
            recipient=user,
            deleted_at__isnull=True,
            is_read=False,
        ).count()
