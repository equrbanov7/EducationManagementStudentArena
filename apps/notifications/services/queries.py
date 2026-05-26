"""
Notification query helpers.
"""

from django.db.models import Q

from apps.notifications.models import InAppNotification


def get_user_notifications(*, user, filter_by: str = "all", notification_type: str = "", search_query: str = ""):
    """
    Return a QuerySet of non-deleted notifications for *user*, ordered
    newest-first.

    Args:
        user: The recipient user.
        filter_by: ``"all"`` | ``"unread"`` | ``"read"``
        notification_type: Optional ``NotificationType`` value to narrow results.
        search_query: Optional search term matched against notification title/message.

    NOTE: A lazy QuerySet is returned. It is scoped by ``recipient=user`` (the
    real security boundary). Because notifications now carry an ``organization``
    FK enforced by RLS, callers that must show a user's FULL inbox regardless
    of the active organisation should evaluate this queryset inside
    ``core.rls.bypass_rls()`` — see ``notifications.views.notification_list``.
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

    normalized_search_query = " ".join(str(search_query or "").split()).strip()
    if normalized_search_query:
        qs = qs.filter(Q(title__icontains=normalized_search_query) | Q(message__icontains=normalized_search_query))

    return qs
