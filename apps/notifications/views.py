"""
apps/notifications/views.py
────────────────────────────
In-app notification views.

Endpoints:
  GET  /notifications/                 – notification inbox (paginated)
  GET  /notifications/<pk>/            – notification detail (marks as read)
  POST /notifications/<pk>/read/       – mark one notification as read
  POST /notifications/<pk>/unread/     – mark one notification as unread
  POST /notifications/read-all/        – mark all as read
  POST /notifications/<pk>/delete/     – soft-delete one notification
  POST /notifications/bulk-delete/     – soft-delete selected notifications
  GET  /notifications/unread-count/    – JSON unread count (for navbar badge)
"""

import logging

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.notifications.models import InAppNotification, NotificationType
from apps.notifications.services import (
    bulk_delete_notifications,
    delete_notification,
    get_unread_count,
    get_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    mark_notification_unread,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 15

# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────


def _get_own_notification_or_404(pk, user):
    """Return InAppNotification if it belongs to *user*, else 404."""
    return get_object_or_404(InAppNotification, pk=pk, recipient=user, deleted_at__isnull=True)


def _safe_next_url(request):
    """Return a safe `next` URL from POST, defaulting to notification list."""
    from urllib.parse import urlparse

    next_url = request.POST.get("next", "").strip()
    if next_url:
        parsed = urlparse(next_url)
        # Only allow relative URLs (no scheme/netloc) for safety
        if not parsed.scheme and not parsed.netloc:
            return next_url
    return None


# ────────────────────────────────────────────────────────────────────────────
# Notification List (Inbox)
# ────────────────────────────────────────────────────────────────────────────


@login_required
def notification_list(request):
    """
    Paginated notification inbox.

    Query params:
      filter  – "all" | "unread" | "read"
      type    – NotificationType value
      page    – page number
    """
    filter_by = request.GET.get("filter", "all")
    type_filter = request.GET.get("type", "")

    # Validate filter_by
    if filter_by not in ("all", "unread", "read"):
        filter_by = "all"

    # Validate type_filter against known types
    valid_types = {t.value for t in NotificationType}
    if type_filter not in valid_types:
        type_filter = ""

    qs = get_user_notifications(
        user=request.user,
        filter_by=filter_by,
        notification_type=type_filter,
    )

    paginator = Paginator(qs, PAGE_SIZE)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    unread_count = get_unread_count(user=request.user)

    return render(
        request,
        "notifications/notification_list.html",
        {
            "page_obj": page_obj,
            "filter_by": filter_by,
            "type_filter": type_filter,
            "notification_types": NotificationType.choices,
            "unread_count": unread_count,
        },
    )


# ────────────────────────────────────────────────────────────────────────────
# Notification Detail
# ────────────────────────────────────────────────────────────────────────────


@login_required
@require_http_methods(["GET"])
def notification_detail(request, pk):
    """Show full notification and mark it as read."""
    notification = _get_own_notification_or_404(pk, request.user)
    mark_notification_read(notification=notification, user=request.user)
    return render(
        request,
        "notifications/notification_detail.html",
        {"notification": notification},
    )


# ────────────────────────────────────────────────────────────────────────────
# Mark Read / Unread
# ────────────────────────────────────────────────────────────────────────────


@login_required
@require_POST
def notification_mark_read(request, pk):
    """Mark a single notification as read."""
    notification = _get_own_notification_or_404(pk, request.user)
    mark_notification_read(notification=notification, user=request.user)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True, "is_read": True})
    return redirect(_safe_next_url(request) or "notifications:notification_list")


@login_required
@require_POST
def notification_mark_unread(request, pk):
    """Mark a single notification as unread."""
    notification = _get_own_notification_or_404(pk, request.user)
    mark_notification_unread(notification=notification, user=request.user)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True, "is_read": False})
    return redirect(_safe_next_url(request) or "notifications:notification_list")


@login_required
@require_POST
def notification_mark_all_read(request):
    """Mark all non-deleted unread notifications as read."""
    count = mark_all_notifications_read(user=request.user)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True, "updated": count})
    return redirect(_safe_next_url(request) or "notifications:notification_list")


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
    return redirect(_safe_next_url(request) or "notifications:notification_list")


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
    return redirect(_safe_next_url(request) or "notifications:notification_list")


# ────────────────────────────────────────────────────────────────────────────
# Unread Count (JSON, for navbar badge)
# ────────────────────────────────────────────────────────────────────────────


@login_required
@require_http_methods(["GET"])
def unread_count(request):
    """Return JSON with the current unread notification count."""
    count = get_unread_count(user=request.user)
    return JsonResponse({"unread_count": count})
