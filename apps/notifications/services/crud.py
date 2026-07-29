"""
Notification create / delete primitives.

The low-level building blocks every ``notify_*`` event function builds on,
plus the soft-delete helpers used by the notification views.
"""

from django.utils import timezone

from apps.notifications.models import InAppNotification, NotificationType
from core.rls import bypass_rls

from .helpers import _assert_owner, _resolve_organization_id, _serialize_metadata, org_scoped_link


def create_notification(
    *,
    recipient,
    title: str,
    message: str = "",
    link: str = "",
    notification_type: str = NotificationType.SYSTEM,
    metadata: dict | None = None,
    organization=None,
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
        organization: Tenant scope. Pass the Organization (or its id) the
            notification belongs to. Leave ``None`` ONLY for genuinely global
            notifications (platform/system, blog). Falls back to a legacy
            ``metadata['organization_id']`` value when not given.

    Returns:
        The newly created :class:`InAppNotification` instance.
    """
    with bypass_rls():
        return InAppNotification.objects.create(
            recipient=recipient,
            organization_id=_resolve_organization_id(organization, metadata),
            title=title,
            message=message,
            link=org_scoped_link(link, organization),
            notification_type=notification_type,
            metadata=_serialize_metadata(metadata or {}),
        )


def create_notification_for_users(
    *,
    recipients,
    title: str,
    message: str = "",
    link: str = "",
    notification_type: str = NotificationType.SYSTEM,
    metadata: dict | None = None,
    organization=None,
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
        organization: Tenant scope shared by all recipients. ``None`` only for
            genuinely global notifications. Falls back to a legacy
            ``metadata['organization_id']`` value when not given.

    Returns:
        List of created :class:`InAppNotification` instances.
    """
    payload = _serialize_metadata(metadata or {})
    org_id = _resolve_organization_id(organization, metadata)
    notifications = [
        InAppNotification(
            recipient=user,
            organization_id=org_id,
            title=title,
            message=message,
            link=org_scoped_link(link, organization),
            notification_type=notification_type,
            metadata=payload,
        )
        for user in recipients
    ]
    if not notifications:
        return []
    with bypass_rls():
        return InAppNotification.objects.bulk_create(notifications)


def delete_notification(*, notification: InAppNotification, user) -> None:
    """
    Soft-delete *notification* for *user*.

    Raises PermissionError if *notification* does not belong to *user*.
    """
    _assert_owner(notification, user)
    with bypass_rls():
        notification.soft_delete()


def bulk_delete_notifications(*, notification_ids: list[int], user) -> int:
    """
    Soft-delete all notifications whose IDs are in *notification_ids* and
    that belong to *user*.  Unknown or other-user IDs are silently ignored.

    Returns the number of notifications deleted.
    """
    now = timezone.now()
    with bypass_rls():
        updated = InAppNotification.objects.filter(
            pk__in=notification_ids,
            recipient=user,
            deleted_at__isnull=True,
        ).update(deleted_at=now)
    return updated
