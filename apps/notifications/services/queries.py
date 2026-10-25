"""
Notification query helpers.
"""

from apps.notifications.models import InAppNotification
from core.search_text import tolerant_q


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
    ``core.rls.bypass_rls()`` — see the cabinet section ``accounts/views/profile/_sections/notifications.py``.
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

    search_q = tolerant_q(search_query, ("title", "message"))
    if search_q is not None:
        qs = qs.filter(search_q)

    return qs


def notified_metadata_values(*, recipient_ids, key: str, match: dict | None = None) -> dict:
    """``{recipient_id: {dəyər, …}}`` — alıcıların bildirişlərindəki ``metadata[key]`` siyahılarının birləşməsi.

    Təkrar bildirişin qarşısı üçün (məs. jurnal: eyni dərsin q/b-si ikinci dəfə bildirilməsin — müəllim
    q/b → i/e → q/b etsə də). ``match`` — ``metadata`` alt-çoxluğu süzgəci (``{"event": …, "offering_id": …}``).
    Silinmiş (``deleted_at``) bildirişlər də sayılır: istifadəçi sildisə, hadisə yenə «bildirilib».
    ``recipient_id`` süzgəci sərhəddir — ``bypass_rls`` (bildiriş istənilən tenant-da ola bilər).
    """
    from core.rls import bypass_rls

    ids = sorted({int(pk) for pk in recipient_ids or [] if pk is not None})
    result: dict = {}
    if not ids or not key:
        return result
    qs = InAppNotification.objects.filter(recipient_id__in=ids, metadata__has_key=key)
    if match:
        qs = qs.filter(metadata__contains=match)
    with bypass_rls():
        rows = list(qs.values_list("recipient_id", f"metadata__{key}"))
    for recipient_id, values in rows:
        if isinstance(values, list):
            result.setdefault(recipient_id, set()).update(str(value) for value in values)
    return result
