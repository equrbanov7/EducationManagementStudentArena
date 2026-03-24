"""
Template tags for the notifications app.
"""

from django import template

from apps.notifications.services import get_unread_count

register = template.Library()


@register.simple_tag
def user_unread_notification_count(user):
    """
    Return the number of unread, non-deleted notifications for *user*.

    Usage::

        {% load notification_tags %}
        {% user_unread_notification_count request.user as count %}
    """
    if not user or not user.is_authenticated:
        return 0
    return get_unread_count(user=user)
