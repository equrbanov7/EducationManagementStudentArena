"""Elanlar şablon tag-ları — kabinet paneli, sidebar sayğacı, birdəfəlik popup.

Tag-lar ``accounts`` şablonlarından ``{% load announcements_tags %}`` ilə çağırılır (Python
importu yoxdur → modul-sərhəd qrafında ``accounts → announcements`` kənarı yaranmır).
"""

from __future__ import annotations

import logging

from django import template
from django.urls import reverse
from django.utils import timezone

from ..constants import ATTACHMENT_ACCEPT, PROFILE_SECTION, Category
from ..services import access, popup, queries
from ..services.apply import apply_closed_reason
from ..services.audience import viewer_for

logger = logging.getLogger(__name__)
register = template.Library()

_BADGE_ATTR = "_ems_announcements_badge"


def _request_parts(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    organization = getattr(request, "organization", None)
    return request, user, organization


@register.simple_tag(takes_context=True)
def announcements_panel(context):
    """Kabinet bölməsinin konteksti: ``?elan=<id>`` → detal, əks halda siyahının 1-ci səhifəsi."""
    request, user, organization = _request_parts(context)
    if request is None or organization is None or not getattr(user, "is_authenticated", False):
        return {"available": False}
    viewer = viewer_for(user, organization, getattr(request, "org_memberships", None))
    profile_url = reverse("accounts:profile")
    panel = {
        "available": True,
        "view_as": bool(getattr(request, "is_view_as", False)),
        "can_manage": access.can_manage(user, organization, request=request),
        "manage_url": reverse("announcements:manage_list"),
        "list_url": reverse("announcements:list"),
        "back_url": f"{profile_url}?section={PROFILE_SECTION}",
        "profile_base_url": profile_url,
        "categories": Category.choices,
    }
    elan = request.GET.get("elan")
    if elan:
        item = queries.get_visible(organization, viewer, elan)
        panel["mode"] = "detail"
        panel["item"] = item
        if item is not None:
            receipt = queries.receipt_for(item, user)
            panel["receipt"] = receipt
            panel["apply_closed"] = apply_closed_reason(item)
            panel["read_url"] = reverse("announcements:read", kwargs={"announcement_id": item.pk})
            panel["apply_url"] = reverse("announcements:apply", kwargs={"announcement_id": item.pk})
        return panel
    params = queries.ListParams.from_query(request.GET)
    panel["mode"] = "list"
    panel["listing"] = queries.user_list(organization, user, viewer, params)
    panel["params"] = params
    return panel


@register.simple_tag(takes_context=True)
def announcements_unread_count(context):
    """Sidebar «Elanlar» badge-i — request üzrə BİR hesab (bənd bir neçə dəfə daxil olunsa belə)."""
    request, user, organization = _request_parts(context)
    if request is None or organization is None or not getattr(user, "is_authenticated", False):
        return 0
    cached = getattr(request, _BADGE_ATTR, None)
    if cached is not None:
        return cached
    try:
        count = popup.badge_count(user, organization, getattr(request, "org_memberships", None))
    except Exception:  # noqa: BLE001 — sayğac sidebar-ı bloklamamalıdır
        logger.warning("announcements badge failed", exc_info=True)
        count = 0
    setattr(request, _BADGE_ATTR, count)
    return count


@register.simple_tag(takes_context=True)
def announcements_popup(context):
    """Gözləyən popup elanları (``[]`` — modal render olunmur)."""
    request = context.get("request")
    if request is None:
        return []
    try:
        return popup.pending_popups(request)
    except Exception:  # noqa: BLE001 — popup heç vaxt səhifəni sındırmır
        logger.warning("announcements popup failed", exc_info=True)
        return []


@register.simple_tag
def announcements_attachment_accept():
    return ATTACHMENT_ACCEPT


@register.filter
def ann_local(value):
    """``datetime-local`` girişi üçün ISO (yerli vaxt)."""
    if not value:
        return ""
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")
