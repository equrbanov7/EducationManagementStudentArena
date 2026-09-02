"""Service layer for contact submissions and replies.

Two delivery paths exist for outbound mail:

1. **SMTP** — Django's standard backend over Brevo SMTP relay. Works
   on most networks but some ISPs block ports 587/465.
2. **Brevo HTTP API** — falls back to ``https://api.brevo.com/v3/smtp/email``
   when SMTP fails. Port 443 is virtually never blocked, so this is
   the most reliable path. Requires ``BREVO_API_KEY`` in the env.

Both paths run in a daemon thread so the HTTP request thread is never
blocked by network I/O — the persisted database row is the source of
truth, email is a best-effort notification on top.
"""

from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.translation import gettext as _

# Outbound mail (SMTP → Brevo HTTP API fallback) lives in ``core.mailing`` so
# every app shares one delivery path. Re-exported with the historical private
# names to preserve this module's internal call-sites unchanged.
from core.mailing import send_email_with_fallback as _send_email_with_fallback
from core.mailing import send_via_brevo_api as _send_via_brevo_api  # noqa: F401  (kept for backwards compat)
from core.utils import build_absolute_url

from .models import ContactMessage

logger = logging.getLogger(__name__)

_DEFAULT_OWNER_EMAIL = "info@emsarena.com"

_REPLY_FROM_EMAILS = {
    "info": "info@emsarena.com",
    "support": "support@emsarena.com",
}


def _resolve_notify_address() -> str:
    """Return the address that should receive contact form notifications."""
    return getattr(settings, "CONTACT_NOTIFY_EMAIL", "") or _DEFAULT_OWNER_EMAIL


# ---------------------------------------------------------------------------
# Internal notification (to staff inbox)
# ---------------------------------------------------------------------------
def _send_internal_notification(message: ContactMessage) -> bool:
    """Send the new-message alert to the configured staff mailbox."""
    recipient = _resolve_notify_address()
    brand = getattr(settings, "SITE_BRAND_NAME", "") or "Qərbi Kaspi Universiteti"
    subject = _("[%(brand)s Contact] %(subject)s — %(name)s") % {
        "brand": brand,
        "subject": message.get_subject_display(),
        "name": message.name,
    }

    reply_url = build_absolute_url(reverse("admin:contact_contactmessage_reply", args=[message.pk]))
    detail_url = build_absolute_url(reverse("admin:contact_contactmessage_change", args=[message.pk]))

    context = {
        "message": message,
        "subject_display": message.get_subject_display(),
        "brand": brand,
        "site_name": brand,
        "reply_url": reply_url,
        "detail_url": detail_url,
    }
    html_body = render_to_string("contact/email/contact_notification.html", context)
    text_body = strip_tags(html_body)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@emsarena.com")
    ok, _reason = _send_email_with_fallback(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        from_email=from_email,
        from_name=brand,
        to=[recipient],
        reply_to=[message.email],
    )
    return ok


def dispatch_contact_notification(message: ContactMessage) -> None:
    """Fire-and-forget background send. HTTP thread never waits."""

    def _runner() -> None:
        _send_internal_notification(message)

    threading.Thread(
        target=_runner,
        name=f"contact-email-{message.pk}",
        daemon=True,
    ).start()


# ---------------------------------------------------------------------------
# Reply to customer
# ---------------------------------------------------------------------------
def _send_reply_email(message: ContactMessage, reply_body: str, reply_from: str) -> tuple[bool, str]:
    """Render and dispatch the reply email. Caller MUST persist already."""
    brand = getattr(settings, "SITE_BRAND_NAME", "") or "Qərbi Kaspi Universiteti"
    from_email = _REPLY_FROM_EMAILS[reply_from]
    from_name = f"{brand} Support" if reply_from == "support" else brand

    subject = _("Re: [%(brand)s] %(subject)s") % {"brand": brand, "subject": message.get_subject_display()}
    context = {
        "message": message,
        "reply_body": reply_body,
        "from_email": from_email,
        "brand": brand,
    }
    html_body = render_to_string("contact/email/contact_reply.html", context)
    text_body = strip_tags(html_body)

    return _send_email_with_fallback(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        from_email=from_email,
        from_name=from_name,
        to=[message.email],
        reply_to=[from_email],
        extra_headers={"X-EMSArena-Reply-To-Message-ID": str(message.pk)},
    )


def send_reply_to_contact(
    *,
    message: ContactMessage,
    reply_body: str,
    reply_from: str,
    sent_by,
) -> bool:
    """Persist the reply and dispatch it asynchronously.

    DB persistence is synchronous so the admin's work survives an SMTP
    failure. The email itself is sent in a daemon thread → the admin's
    HTTP response is returned immediately, never blocked on the network.

    Returns True (always) — the caller treats success as "the reply has
    been recorded". Email delivery status is tracked on the message row.
    """
    from django.utils import timezone

    if reply_from not in _REPLY_FROM_EMAILS:
        raise ValueError(f"Unknown reply_from inbox: {reply_from!r}")

    # ---- Persist FIRST (cheap, transactional) ----
    message.reply_body = reply_body
    message.reply_from = reply_from
    message.reply_sent_by = sent_by
    message.reply_delivery_status = ContactMessage.REPLY_DELIVERY_PENDING
    message.reply_delivery_error = ""
    message.reply_sent_at = None
    message.is_handled = False
    message.handled_at = None
    message.save(
        update_fields=[
            "reply_body",
            "reply_from",
            "reply_sent_by",
            "reply_delivery_status",
            "reply_delivery_error",
            "reply_sent_at",
            "is_handled",
            "handled_at",
        ]
    )

    # ---- Dispatch in background (never blocks the request) ----
    def _runner() -> None:
        try:
            ok, reason = _send_reply_email(message, reply_body, reply_from)
            sent_at = timezone.now()
            if not ok:
                ContactMessage.objects.filter(pk=message.pk).update(
                    reply_delivery_status=ContactMessage.REPLY_DELIVERY_FAILED,
                    reply_delivery_error=reason[:500],
                )
                logger.error(
                    "Contact reply email failed via SMTP and API: %s",
                    reason,
                    extra={"contact_message_id": message.pk},
                )
                return

            ContactMessage.objects.filter(pk=message.pk).update(
                reply_delivery_status=ContactMessage.REPLY_DELIVERY_SENT,
                reply_delivery_error="",
                reply_sent_at=sent_at,
                is_handled=True,
                handled_at=sent_at,
            )
        except Exception:
            logger.exception(
                "Contact reply background worker failed",
                extra={"contact_message_id": message.pk},
            )

    threading.Thread(
        target=_runner,
        name=f"contact-reply-{message.pk}",
        daemon=True,
    ).start()
    return True


# ---------------------------------------------------------------------------
# Public form entry point
# ---------------------------------------------------------------------------
def create_contact_message(*, form_cleaned_data: dict, request) -> ContactMessage:
    """Persist a contact message and trigger asynchronous notification."""
    ip = _extract_client_ip(request)
    user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:512]

    message = ContactMessage.objects.create(
        name=form_cleaned_data["name"],
        email=form_cleaned_data["email"],
        phone=form_cleaned_data.get("phone", "") or "",
        subject=form_cleaned_data["subject"],
        message=form_cleaned_data["message"],
        ip_address=ip,
        user_agent=user_agent,
    )
    dispatch_contact_notification(message)
    return message


def _extract_client_ip(request) -> str | None:
    """Vahid ``core.utils.get_client_ip`` helperinə həvalə (2026-09-02 audit, P2-6).

    Əvvəl XFF-in ƏN SOL üzvü götürülürdü — onu müştəri özü yazır, yəni per-IP
    limit saxtalaşdırıla bilirdi.  Artıq etibarlı proxy semantikası (sağdan).
    """
    from core.utils import get_client_ip

    return get_client_ip(request)
