"""
Notification aggregation service.

This app is intentionally started as a service layer first so future
notification channels (in-app, email, push, websocket) can be added
without coupling UI logic to accounts views.
"""

import logging

from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.notifications.models import (
    InAppNotification,
    NotificationType,
    StudentOrganizationRequest,
    StudentOrganizationRequestStatus,
)
from apps.organizations.models import Membership

logger = logging.getLogger(__name__)

STUDENT_PENDING_INVITE_TITLE = "__student_pending_invite__"


# ────────────────────────────────────────────────────────────────────────────
# In-App Notification Service
# ────────────────────────────────────────────────────────────────────────────


def create_notification(
    *,
    recipient,
    title: str,
    message: str = "",
    link: str = "",
    notification_type: str = NotificationType.SYSTEM,
    metadata: dict | None = None,
) -> InAppNotification:
    """
    Create a single in-app notification for *recipient*.

    Args:
        recipient: User instance that will receive the notification.
        title: Short notification title (max 255 chars).
        message: Optional full notification body.
        link: Optional URL the notification points to.
        notification_type: One of the ``NotificationType`` choices.
        metadata: Optional free-form dict stored as JSON.

    Returns:
        The newly created :class:`InAppNotification` instance.
    """
    return InAppNotification.objects.create(
        recipient=recipient,
        title=title,
        message=message,
        link=link,
        notification_type=notification_type,
        metadata=metadata or {},
    )


def create_notification_for_users(
    *,
    recipients,
    title: str,
    message: str = "",
    link: str = "",
    notification_type: str = NotificationType.SYSTEM,
    metadata: dict | None = None,
) -> list[InAppNotification]:
    """
    Create the same notification for multiple users in a single bulk insert.

    Args:
        recipients: Iterable of User instances.
        title: Short notification title.
        message: Optional notification body.
        link: Optional target URL.
        notification_type: One of the ``NotificationType`` choices.
        metadata: Optional free-form dict (shared across all recipients).

    Returns:
        List of created :class:`InAppNotification` instances.
    """
    payload = metadata or {}
    notifications = [
        InAppNotification(
            recipient=user,
            title=title,
            message=message,
            link=link,
            notification_type=notification_type,
            metadata=payload,
        )
        for user in recipients
    ]
    return InAppNotification.objects.bulk_create(notifications)


# ────────────────────────────────────────────────────────────────────────────
# Read / Unread helpers
# ────────────────────────────────────────────────────────────────────────────


def mark_notification_read(*, notification: InAppNotification, user) -> bool:
    """
    Mark *notification* as read for *user*.

    Returns True if the state changed, False if it was already read.
    Raises PermissionError if *notification* does not belong to *user*.
    """
    _assert_owner(notification, user)
    if notification.is_read:
        return False
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
    notification.mark_unread()
    return True


def mark_all_notifications_read(*, user) -> int:
    """
    Mark all non-deleted, unread notifications for *user* as read.

    Returns the number of notifications updated.
    """
    now = timezone.now()
    updated = InAppNotification.objects.filter(
        recipient=user,
        deleted_at__isnull=True,
        is_read=False,
    ).update(is_read=True, read_at=now)
    return updated


# ────────────────────────────────────────────────────────────────────────────
# Delete helpers
# ────────────────────────────────────────────────────────────────────────────


def delete_notification(*, notification: InAppNotification, user) -> None:
    """
    Soft-delete *notification* for *user*.

    Raises PermissionError if *notification* does not belong to *user*.
    """
    _assert_owner(notification, user)
    notification.soft_delete()


def bulk_delete_notifications(*, notification_ids: list[int], user) -> int:
    """
    Soft-delete all notifications whose IDs are in *notification_ids* and
    that belong to *user*.  Unknown or other-user IDs are silently ignored.

    Returns the number of notifications deleted.
    """
    now = timezone.now()
    updated = InAppNotification.objects.filter(
        pk__in=notification_ids,
        recipient=user,
        deleted_at__isnull=True,
    ).update(deleted_at=now)
    return updated


# ────────────────────────────────────────────────────────────────────────────
# Query helpers
# ────────────────────────────────────────────────────────────────────────────


def get_user_notifications(*, user, filter_by: str = "all", notification_type: str = ""):
    """
    Return a QuerySet of non-deleted notifications for *user*, ordered
    newest-first.

    Args:
        user: The recipient user.
        filter_by: ``"all"`` | ``"unread"`` | ``"read"``
        notification_type: Optional ``NotificationType`` value to narrow results.
    """
    qs = InAppNotification.objects.filter(
        recipient=user,
        deleted_at__isnull=True,
    ).order_by("-created_at")

    if filter_by == "unread":
        qs = qs.filter(is_read=False)
    elif filter_by == "read":
        qs = qs.filter(is_read=True)

    if notification_type:
        qs = qs.filter(notification_type=notification_type)

    return qs


def get_unread_count(*, user) -> int:
    """Return the number of non-deleted unread notifications for *user*."""
    return InAppNotification.objects.filter(
        recipient=user,
        deleted_at__isnull=True,
        is_read=False,
    ).count()


# ────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ────────────────────────────────────────────────────────────────────────────


def _assert_owner(notification: InAppNotification, user) -> None:
    if notification.recipient_id != user.pk:
        raise PermissionError("You can only manage your own notifications.")


def build_profile_notification_state(*, user, profile):
    pending_student_invites = (
        Membership.objects.filter(
            user=user,
            is_active=False,
            title=STUDENT_PENDING_INVITE_TITLE,
            organization__is_active=True,
            organization__status="active",
        )
        .select_related("organization", "assigned_by", "role")
        .order_by("organization__name")
    )

    pending_student_join_requests = []
    pending_student_join_org_name = ""
    pending_student_join_message = ""
    if profile.organization is None and profile.role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}:
        pending_student_join_requests = list(
            StudentOrganizationRequest.objects.filter(
                user=user,
                status=StudentOrganizationRequestStatus.PENDING,
                organization__is_active=True,
                organization__status="active",
            )
            .select_related("organization")
            .order_by("-created_at")
        )

        if pending_student_join_requests:
            latest_request = pending_student_join_requests[0]
            pending_student_join_org_name = latest_request.organization.name
            pending_student_join_message = (latest_request.message or "").strip()

    student_can_leave_org = bool(
        profile.organization
        and (
            profile.role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}
            or Membership.objects.filter(
                user=user,
                organization=profile.organization,
                is_active=True,
                role__name="student",
            ).exists()
        )
    )

    unread_count = pending_student_invites.count() + len(pending_student_join_requests)

    return {
        "pending_student_invites": pending_student_invites,
        "pending_student_join_requests": pending_student_join_requests,
        "pending_student_join_org_name": pending_student_join_org_name,
        "pending_student_join_message": pending_student_join_message,
        "student_can_leave_org": student_can_leave_org,
        "unread_count": unread_count,
    }
