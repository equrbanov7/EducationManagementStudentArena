"""Contact messages inbox embedded in the user profile.

Provides context data for the ``superadmin-contact-messages`` section
and handles the inline reply POST. Access is gated by the
``'superadmin-contact-messages'`` membership in ``allowed_sections``,
which itself is restricted to superadmins by ``_helpers.rbac``.
"""

from __future__ import annotations

import logging

from django.contrib import messages as django_messages
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.contact.models import ContactMessage
from apps.contact.services import send_reply_to_contact

logger = logging.getLogger(__name__)

CONTACT_LIST_LIMIT = 50
CONTACT_SIDEBAR_BADGE_LIMIT = 99  # cap so the badge stays compact


def _can_access_contact_inbox(capabilities: dict) -> bool:
    """Single source of truth for the access gate."""
    return bool(capabilities.get("is_superadmin")) and (
        "superadmin-contact-messages" in capabilities.get("allowed_sections", set())
    )


def build_contact_inbox_context(
    request: HttpRequest,
    *,
    capabilities: dict,
    active_section: str,
) -> dict:
    """Return template context for the contact inbox section.

    The sidebar badge (``contact_unhandled_count``) is computed on every
    profile page render — it's a single COUNT(*) query so the cost is
    negligible. The full list is only loaded when the section is
    actually being viewed.
    """
    if not _can_access_contact_inbox(capabilities):
        return {}

    ctx: dict = {
        "contact_unhandled_count": min(
            ContactMessage.objects.filter(is_handled=False).count(),
            CONTACT_SIDEBAR_BADGE_LIMIT,
        ),
    }

    if active_section != "superadmin-contact-messages":
        return ctx

    qs = ContactMessage.objects.all().select_related("reply_sent_by")
    search_query = (request.GET.get("q") or "").strip()[:200]
    if search_query:
        qs = qs.filter(
            Q(name__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(message__icontains=search_query)
            | Q(reply_body__icontains=search_query)
        )

    qs_ordered = qs.order_by("-created_at")
    ctx.update(
        {
            "contact_messages_list": list(qs_ordered[:CONTACT_LIST_LIMIT]),
            "contact_total_count": ContactMessage.objects.count(),
            "contact_replied_count": ContactMessage.objects.filter(
                reply_delivery_status=ContactMessage.REPLY_DELIVERY_SENT
            ).count(),
            "contact_failed_count": ContactMessage.objects.filter(
                reply_delivery_status=ContactMessage.REPLY_DELIVERY_FAILED
            ).count(),
            "contact_pending_count": ContactMessage.objects.filter(
                reply_delivery_status=ContactMessage.REPLY_DELIVERY_PENDING
            ).count(),
            "contact_recorded_count": ContactMessage.objects.filter(
                reply_delivery_status=ContactMessage.REPLY_DELIVERY_RECORDED
            ).count(),
            "contact_search_query": search_query,
        }
    )

    # Detail view (one message + reply form) when ?message_id=N
    message_id = (request.GET.get("message_id") or "").strip()
    if message_id.isdigit():
        selected = ContactMessage.objects.filter(pk=int(message_id)).first()
        if selected is not None:
            ctx["contact_selected_message"] = selected

    return ctx


def handle_contact_reply_post(
    request: HttpRequest,
    *,
    capabilities: dict,
) -> "HttpResponse | None":
    """Handle the inline reply POST. Returns a redirect on success/error,
    or None if this POST is not addressed to the contact inbox."""
    if request.POST.get("action") != "contact_reply":
        return None

    if not _can_access_contact_inbox(capabilities):
        django_messages.error(request, _("Bu əməliyyat üçün icazəniz yoxdur."))
        return redirect(reverse("accounts:profile"))

    message_id = (request.POST.get("message_id") or "").strip()
    if not message_id.isdigit():
        django_messages.error(request, _("Mesaj tapılmadı."))
        return redirect(reverse("accounts:profile") + "?section=superadmin-contact-messages")

    message = ContactMessage.objects.filter(pk=int(message_id)).first()
    if message is None:
        django_messages.error(request, _("Mesaj tapılmadı."))
        return redirect(reverse("accounts:profile") + "?section=superadmin-contact-messages")

    reply_body = (request.POST.get("reply_body") or "").strip()
    reply_from = (request.POST.get("reply_from") or "info").strip()

    if len(reply_body) < 10:
        django_messages.error(request, _("Cavab mətni ən azı 10 simvol olmalıdır."))
        return redirect(f"{reverse('accounts:profile')}?section=superadmin-contact-messages&message_id={message.pk}")
    if len(reply_body) > 10000:
        django_messages.error(request, _("Cavab mətni 10000 simvoldan uzun ola bilməz."))
        return redirect(f"{reverse('accounts:profile')}?section=superadmin-contact-messages&message_id={message.pk}")
    if reply_from not in {"info", "support"}:
        django_messages.error(request, _("Yanlış göndərən ünvanı."))
        return redirect(f"{reverse('accounts:profile')}?section=superadmin-contact-messages&message_id={message.pk}")

    send_reply_to_contact(
        message=message,
        reply_body=reply_body,
        reply_from=reply_from,
        sent_by=request.user,
    )
    django_messages.success(
        request,
        _("Cavab qeyd edildi və %(email)s ünvanına göndərilməyə çalışılır.") % {"email": message.email},
    )
    return redirect(f"{reverse('accounts:profile')}?section=superadmin-contact-messages&message_id={message.pk}")
