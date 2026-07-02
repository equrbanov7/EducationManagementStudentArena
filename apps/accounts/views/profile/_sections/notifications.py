"""Profil "notifications" bölməsi üçün context-fragment qurucusu."""

from django.core.paginator import Paginator

from apps.accounts.views._helpers.formatting import _query_string
from apps.accounts.views.profile.search import _normalize_public_profile_query_value
from apps.notifications.models import NotificationType
from apps.notifications.public import get_user_notifications
from core.rls import bypass_rls


def _defaults() -> dict:
    return {
        "notif_filter": "all",
        "notif_type": "",
        "notif_search_query": "",
        "notif_pagination_query": "",
        "in_app_notifications_page": None,
    }


def build_notifications_context(request, *, active_section) -> dict:
    """In-app bildiriş siyahısı bölməsi üçün ``context`` açarları. Bölmə aktiv
    deyilsə default-lar (sidebar yalnız sayğacdan istifadə edir). Davranış köhnə
    inline blokla eynidir."""
    if active_section != "notifications":
        return _defaults()

    notif_filter = request.GET.get("notif_filter", "all")
    if notif_filter not in ("all", "unread", "read"):
        notif_filter = "all"
    # Tip filtri — yalnız mövcud NotificationType dəyərləri qəbul olunur.
    notif_type = request.GET.get("notif_type", "")
    if notif_type not in {t.value for t in NotificationType}:
        notif_type = ""
    notif_search_query = _normalize_public_profile_query_value(
        request.GET.get("notif_search"),
        max_length=100,
    )
    in_app_notifications_qs = get_user_notifications(
        user=request.user,
        filter_by=notif_filter,
        notification_type=notif_type,
        search_query=notif_search_query,
    )
    # recipient=user is the security boundary; bypass RLS so the profile inbox
    # shows the user's notifications across every organisation (see
    # get_user_notifications docstring).
    in_app_notifications_paginator = Paginator(in_app_notifications_qs, 10)
    with bypass_rls():
        in_app_notifications_page = in_app_notifications_paginator.get_page(request.GET.get("notif_page", 1))
        in_app_notifications_page.object_list = list(in_app_notifications_page.object_list)
    notif_pagination_query = _query_string(
        section="notifications",
        notif_filter=notif_filter,
        notif_type=notif_type,
        notif_search=notif_search_query,
    )
    return {
        "notif_filter": notif_filter,
        "notif_type": notif_type,
        "notif_search_query": notif_search_query,
        "notif_pagination_query": notif_pagination_query,
        "in_app_notifications_page": in_app_notifications_page,
    }
