"""
apps/notifications/views.py
────────────────────────────
In-app notification actions (the inbox itself is the cabinet section
``/accounts/profile/?section=notifications``).

Endpoints:
  POST /notifications/<pk>/read/       – mark one notification as read
  POST /notifications/read-all/        – mark all as read
  POST /notifications/<pk>/delete/     – soft-delete one notification
  POST /notifications/bulk-delete/     – soft-delete selected notifications

WP9a (2026-10-10): müstəqil səhifələr (`notifications/`, `<pk>/`), `<pk>/unread/` və
`unread-count/` silindi — kabinet bölməsi onları işlətmirdi.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.notifications.models import InAppNotification
from apps.notifications.services import (
    bulk_delete_notifications,
    delete_notification,
    mark_all_notifications_read,
    mark_notification_read,
)
from core.rls import bypass_rls

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _get_own_notification_or_404(pk, user):
    """Return InAppNotification if it belongs to *user*, else 404.

    Runs under bypass_rls(): ``recipient=user`` is the security boundary, and a
    user must be able to open/mark/delete their own notification regardless of
    which organisation (if any) is currently active in the session.
    """
    with bypass_rls():
        return get_object_or_404(InAppNotification, pk=pk, recipient=user, deleted_at__isnull=True)


def _cabinet_notifications_url():
    """Bildiriş qutusu kabinet bölməsidir (WP9a 2026-10-10: köhnə `notifications/` səhifəsi silindi)."""
    from django.urls import reverse

    return f"{reverse('accounts:profile')}?section=notifications"


def _safe_next_url(request):
    """Return a safe `next` URL from POST (``None`` → caller falls back to the cabinet inbox).

    Təhlükəsizlik auditi 2026-10-07: əvvəl ``urlparse`` ilə «sxem/host yoxdur»
    yoxlanırdı — ``/\\evil.example`` (və tab/CR qarışıq yollar) keçirdi, brauzer
    isə onu ``//evil.example`` kimi açır. İndi Django-nun öz yoxlaması.
    """
    from django.urls import reverse
    from django.utils.http import url_has_allowed_host_and_scheme

    next_url = request.POST.get("next", "").strip()
    if next_url:
        if next_url.startswith("?"):
            next_url = f"{reverse('accounts:profile')}{next_url}"
        if url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return next_url
    return None


# ────────────────────────────────────────────────────────────────────────────
# Mark Read
# ────────────────────────────────────────────────────────────────────────────


@login_required
@require_POST
def notification_mark_read(request, pk):
    """Mark a single notification as read."""
    notification = _get_own_notification_or_404(pk, request.user)
    mark_notification_read(notification=notification, user=request.user)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True, "is_read": True})
    return redirect(_safe_next_url(request) or _cabinet_notifications_url())


@login_required
@require_POST
def notification_mark_all_read(request):
    """Mark all non-deleted unread notifications as read."""
    count = mark_all_notifications_read(user=request.user)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True, "updated": count})
    return redirect(_safe_next_url(request) or _cabinet_notifications_url())


# ────────────────────────────────────────────────────────────────────────────
# Delete
# ────────────────────────────────────────────────────────────────────────────


@login_required
@require_POST
def notification_delete(request, pk):
    """Soft-delete a single notification."""
    notification = _get_own_notification_or_404(pk, request.user)
    delete_notification(notification=notification, user=request.user)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True})
    return redirect(_safe_next_url(request) or _cabinet_notifications_url())


@login_required
@require_POST
def notification_bulk_delete(request):
    """Soft-delete the notifications whose IDs are in POST['ids[]']."""
    raw_ids = request.POST.getlist("ids[]")
    try:
        notification_ids = [int(i) for i in raw_ids if i.strip()]
    except ValueError:
        return JsonResponse({"success": False, "error": "Invalid ID list."}, status=400)

    deleted = bulk_delete_notifications(notification_ids=notification_ids, user=request.user)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True, "deleted": deleted})
    return redirect(_safe_next_url(request) or _cabinet_notifications_url())
