"""
Template tags for the notifications app.
"""

from django import template

from apps.notifications.services import get_unread_count

register = template.Library()


@register.simple_tag(takes_context=True)
def user_unread_notification_count(context, user):
    """
    Return the number of unread, non-deleted notifications for *user*.

    Usage::

        {% load notification_tags %}
        {% user_unread_notification_count request.user as count %}

    2026-09-13 (Codex audit §14/§21 — kabinet qabığı sorğu büdcəsi): navbar bu
    tag-ı iki dəfə (masaüstü menyu + mobil sıra) çağırır, kabinet qabığı isə eyni
    rəqəmi ``in_app_unread_count`` kimi kontekstə artıq qoyur — hər çağırış
    ``bypass_rls`` bloku ilə 4 SQL ifadəsi idi (12 ifadə / səhifə). Kontekstdə
    EYNİ istifadəçi üçün hazır say varsa o qaytarılır; başqa səhifələrdə (say
    kontekstdə yoxdur) davranış əvvəlki kimi canlı sorğudur.
    """
    if not user or not user.is_authenticated:
        return 0
    precomputed = context.get("in_app_unread_count")
    request = context.get("request")
    if (
        isinstance(precomputed, int)
        and request is not None
        and getattr(getattr(request, "user", None), "pk", None) == getattr(user, "pk", None)
    ):
        return precomputed
    return get_unread_count(user=user)
