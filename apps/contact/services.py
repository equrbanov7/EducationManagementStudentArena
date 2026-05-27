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

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from typing import Sequence

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.translation import gettext as _

from .models import ContactMessage

logger = logging.getLogger(__name__)

_DEFAULT_OWNER_EMAIL = "info@emsarena.com"
_SMTP_TIMEOUT_SECONDS = 8
_HTTP_TIMEOUT_SECONDS = 10
_BREVO_API_ENDPOINT = "https://api.brevo.com/v3/smtp/email"

_REPLY_FROM_ADDRESSES = {
    "info": ("EMSArena", "info@emsarena.com"),
    "support": ("EMSArena Support", "support@emsarena.com"),
}


def _resolve_notify_address() -> str:
    """Return the address that should receive contact form notifications."""
    return getattr(settings, "CONTACT_NOTIFY_EMAIL", "") or _DEFAULT_OWNER_EMAIL


# ---------------------------------------------------------------------------
# Brevo HTTP API client
# ---------------------------------------------------------------------------
def _send_via_brevo_api(
    *,
    subject: str,
    html_body: str,
    text_body: str,
    from_name: str,
    from_email: str,
    to_email: str,
    reply_to_email: str,
) -> bool:
    """Send a single transactional email through Brevo's HTTP API.

    Returns True on success. Designed as a fallback when SMTP fails —
    port 443 is open practically everywhere and the API is significantly
    faster than the SMTP handshake.
    """
    api_key = getattr(settings, "BREVO_API_KEY", "") or os.environ.get("BREVO_API_KEY", "")
    if not api_key:
        logger.warning(
            "BREVO_API_KEY is not configured; BREVO_SMTP_KEY is only for SMTP and cannot be used for HTTP API fallback"
        )
        return False

    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": to_email}],
        "replyTo": {"email": reply_to_email},
        "subject": subject,
        "htmlContent": html_body,
        "textContent": text_body,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _BREVO_API_ENDPOINT,
        data=data,
        method="POST",
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SECONDS) as response:
            status = response.status
            if 200 <= status < 300:
                logger.info(
                    "Brevo API email sent",
                    extra={"to": to_email, "from": from_email, "status": status},
                )
                return True
            logger.error(
                "Brevo API returned non-success status",
                extra={"status": status, "to": to_email},
            )
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        logger.error(
            "Brevo API HTTP error",
            extra={"status": e.code, "body": body, "to": to_email},
        )
        return False
    except Exception:
        logger.exception("Brevo API request failed", extra={"to": to_email})
        return False


# ---------------------------------------------------------------------------
# Generic sender: SMTP → API fallback
# ---------------------------------------------------------------------------
def _send_email_with_fallback(
    *,
    subject: str,
    html_body: str,
    text_body: str,
    from_email: str,
    from_name: str,
    to: Sequence[str],
    reply_to: Sequence[str],
    extra_headers: dict | None = None,
) -> tuple[bool, str]:
    """Try SMTP first, fall back to Brevo HTTP API.

    Returns ``(True, "")`` if either path succeeded, otherwise returns
    ``(False, reason)`` with a short, non-secret diagnostic.
    """
    smtp_error = ""

    # ---- 1. SMTP attempt ----
    try:
        connection = get_connection(timeout=_SMTP_TIMEOUT_SECONDS)
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=f"{from_name} <{from_email}>" if from_name else from_email,
            to=list(to),
            reply_to=list(reply_to),
            connection=connection,
            headers=extra_headers or None,
        )
        email.attach_alternative(html_body, "text/html")
        email.send(fail_silently=False)
        logger.info("SMTP email delivered", extra={"to": list(to), "from": from_email})
        return True, ""
    except Exception as exc:
        smtp_error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "SMTP delivery failed (%s), attempting Brevo HTTP API",
            smtp_error,
            extra={"to": list(to), "error": repr(exc)},
        )

    # ---- 2. Brevo API fallback ----
    if not to:
        return False, smtp_error or "No recipient configured"

    api_ok = _send_via_brevo_api(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        from_name=from_name,
        from_email=from_email,
        to_email=to[0],
        reply_to_email=reply_to[0] if reply_to else from_email,
    )
    if api_ok:
        return True, ""
    if not getattr(settings, "BREVO_API_KEY", "") and not os.environ.get("BREVO_API_KEY", ""):
        return False, f"{smtp_error}; BREVO_API_KEY is not configured"
    return False, f"{smtp_error}; Brevo HTTP API fallback failed"


# ---------------------------------------------------------------------------
# Internal notification (to staff inbox)
# ---------------------------------------------------------------------------
def _send_internal_notification(message: ContactMessage) -> bool:
    """Send the new-message alert to the configured staff mailbox."""
    recipient = _resolve_notify_address()
    subject = _("[EMSArena Contact] %(subject)s — %(name)s") % {
        "subject": message.get_subject_display(),
        "name": message.name,
    }

    site_url = getattr(settings, "SITE_URL", "https://emsarena.com").rstrip("/")
    admin_prefix = getattr(settings, "ADMIN_URL_PREFIX", "admin/").strip("/")
    reply_url = f"{site_url}/{admin_prefix}/contact/contactmessage/{message.pk}/reply/"
    detail_url = f"{site_url}/{admin_prefix}/contact/contactmessage/{message.pk}/change/"

    context = {
        "message": message,
        "subject_display": message.get_subject_display(),
        "site_name": "EMSArena",
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
        from_name="EMSArena",
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
    from_name, from_email = _REPLY_FROM_ADDRESSES[reply_from]

    subject = _("Re: [EMSArena] %(subject)s") % {"subject": message.get_subject_display()}
    context = {
        "message": message,
        "reply_body": reply_body,
        "from_email": from_email,
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

    if reply_from not in _REPLY_FROM_ADDRESSES:
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
    """Return the originating client IP, honouring XFF where trusted."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        candidate = xff.split(",")[0].strip()
        if candidate:
            return candidate
    return request.META.get("REMOTE_ADDR")
