"""Shared transactional email sender.

A single, reusable outbound-email helper with an automatic two-path
delivery strategy. Originally lived inside ``apps.contact.services``; it
was extracted here so any app (contact, trial exams, …) can send mail
through exactly one battle-tested code path instead of duplicating the
SMTP/HTTP fallback logic.

Delivery paths
--------------
1. **SMTP** — Django's standard backend over the Brevo SMTP relay. Works
   on most networks but some ISPs block ports 587/465.
2. **Brevo HTTP API** — falls back to ``https://api.brevo.com/v3/smtp/email``
   when SMTP fails. Port 443 is virtually never blocked, so this is the
   most reliable path. Requires ``BREVO_API_KEY`` in the env.

Both paths are synchronous; callers that must not block the request
thread should invoke :func:`send_email_with_fallback` from inside a
daemon thread (see ``apps.contact.services`` / ``apps.trial_exams.services``).
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Sequence

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

logger = logging.getLogger(__name__)

_SMTP_TIMEOUT_SECONDS = 8
_HTTP_TIMEOUT_SECONDS = 10
_BREVO_API_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


def _brevo_api_key() -> str:
    """Return the configured Brevo HTTP API key, or an empty string."""
    return getattr(settings, "BREVO_API_KEY", "") or os.environ.get("BREVO_API_KEY", "")


def send_via_brevo_api(
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

    Returns ``True`` on success. Designed as a fallback when SMTP fails —
    port 443 is open practically everywhere and the API is significantly
    faster than the SMTP handshake.
    """
    api_key = _brevo_api_key()
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


def send_email_with_fallback(
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

    api_ok = send_via_brevo_api(
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
    if not _brevo_api_key():
        return False, f"{smtp_error}; BREVO_API_KEY is not configured"
    return False, f"{smtp_error}; Brevo HTTP API fallback failed"
