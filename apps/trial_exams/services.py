"""Service layer for trial-exam requests.

Responsibilities
----------------
1. Persist a submission (PDF stored with a randomised filename).
2. Notify the team:
   * an **email** to the configured owner inbox (``TRIAL_NOTIFY_EMAIL`` →
     falls back to ``CONTACT_NOTIFY_EMAIL`` → ``info@emsarena.com``), and
   * an **in-app notification** to every active superadmin.
3. Send the student an **email confirmation** once the questions are
   imported ("suallar sistemə əlavə olundu").

All email I/O runs in a daemon thread — the persisted DB row is the source
of truth, email/notifications are best-effort on top. Mail delivery uses the
shared ``core.mailing`` sender (SMTP → Brevo HTTP API fallback).
"""

from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.translation import gettext as _

from core.mailing import send_email_with_fallback
from core.upload_security import randomize_uploaded_filename
from core.utils import build_absolute_url

from .models import TrialExamRequest

logger = logging.getLogger(__name__)

_DEFAULT_OWNER_EMAIL = "info@emsarena.com"

_REPLY_FROM_ADDRESSES = {
    "info": ("EMSArena", "info@emsarena.com"),
    "support": ("EMSArena Support", "support@emsarena.com"),
}


def _resolve_notify_address() -> str:
    """Return the address that should receive trial-request notifications."""
    return (
        getattr(settings, "TRIAL_NOTIFY_EMAIL", "")
        or getattr(settings, "CONTACT_NOTIFY_EMAIL", "")
        or _DEFAULT_OWNER_EMAIL
    )


def _admin_links(request_obj: TrialExamRequest) -> tuple[str, str]:
    """Return absolute ``(reply_url, detail_url)`` into the Django admin."""
    reply_path = reverse("admin:trial_exams_trialexamrequest_reply", args=[request_obj.pk])
    detail_path = reverse("admin:trial_exams_trialexamrequest_change", args=[request_obj.pk])
    return build_absolute_url(reply_path), build_absolute_url(detail_path)


def _profile_detail_url(request_obj: TrialExamRequest) -> str:
    """Return the superadmin profile inbox URL for this trial request."""
    path = f"{reverse('accounts:profile')}?section=superadmin-contact-messages&trial_id={request_obj.pk}"
    return build_absolute_url(path)


def _file_download_url(request_obj: TrialExamRequest) -> str:
    """Return an absolute protected-media URL for the uploaded PDF."""
    if not request_obj.questions_file:
        return ""
    return build_absolute_url(request_obj.questions_file.url)


# ---------------------------------------------------------------------------
# Inbound notifications (team)
# ---------------------------------------------------------------------------
def _send_owner_notification(request_obj: TrialExamRequest) -> bool:
    """Email the configured owner inbox about a new trial request."""
    recipient = _resolve_notify_address()
    subject = _("[EMSArena Sınaq] %(subject)s — %(name)s") % {
        "subject": request_obj.subject_name,
        "name": request_obj.full_name,
    }
    reply_url, admin_detail_url = _admin_links(request_obj)
    profile_detail_url = _profile_detail_url(request_obj)
    brand = getattr(settings, "SITE_BRAND_NAME", "") or "EMSArena"
    context = {
        "request_obj": request_obj,
        "brand": brand,
        "site_name": brand,
        "reply_url": reply_url,
        "detail_url": profile_detail_url,
        "profile_detail_url": profile_detail_url,
        "admin_detail_url": admin_detail_url,
        "file_download_url": _file_download_url(request_obj),
    }
    html_body = render_to_string("trial_exams/email/trial_notification.html", context)
    text_body = strip_tags(html_body)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@emsarena.com")
    ok, _reason = send_email_with_fallback(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        from_email=from_email,
        from_name="EMSArena",
        to=[recipient],
        reply_to=[request_obj.email],
    )
    return ok


def _notify_superadmins(request_obj: TrialExamRequest) -> None:
    """Create an in-app notification for every active superadmin."""
    # Imported lazily to avoid app-loading ordering issues.
    from django.contrib.auth import get_user_model

    from apps.notifications.models import NotificationType
    from apps.notifications.public import create_notification_for_users

    User = get_user_model()
    admins = list(User.objects.filter(is_superuser=True, is_active=True))
    if not admins:
        return

    detail_url = _profile_detail_url(request_obj)
    title = _("Yeni sınaq imtahanı sorğusu")
    message = _("%(name)s “%(subject)s” fənni üçün sual faylı göndərdi.") % {
        "name": request_obj.full_name,
        "subject": request_obj.subject_name,
    }
    create_notification_for_users(
        recipients=admins,
        title=title,
        message=message,
        link=detail_url,
        notification_type=NotificationType.SYSTEM,
        metadata={"trial_request_id": request_obj.pk, "kind": "trial_exam_request"},
        organization=None,
    )


def dispatch_trial_notifications(request_obj: TrialExamRequest) -> None:
    """Fire-and-forget background dispatch. The HTTP thread never waits."""

    def _runner() -> None:
        try:
            _send_owner_notification(request_obj)
        except Exception:
            logger.exception("Trial owner email failed", extra={"trial_request_id": request_obj.pk})
        try:
            _notify_superadmins(request_obj)
        except Exception:
            logger.exception("Trial admin in-app notification failed", extra={"trial_request_id": request_obj.pk})

    threading.Thread(
        target=_runner,
        name=f"trial-notify-{request_obj.pk}",
        daemon=True,
    ).start()


# ---------------------------------------------------------------------------
# Reply to the student ("questions added")
# ---------------------------------------------------------------------------
def _send_reply_email(request_obj: TrialExamRequest, reply_body: str, reply_from: str) -> tuple[bool, str]:
    """Render and dispatch the confirmation email. Caller MUST persist first."""
    from_name, from_email = _REPLY_FROM_ADDRESSES[reply_from]

    subject = _("EMSArena — Sınaq imtahanınız hazırdır: %(subject)s") % {"subject": request_obj.subject_name}
    context = {
        "request_obj": request_obj,
        "reply_body": reply_body,
        "from_email": from_email,
        "brand": getattr(settings, "SITE_BRAND_NAME", "") or "EMSArena",
    }
    html_body = render_to_string("trial_exams/email/trial_reply.html", context)
    text_body = strip_tags(html_body)

    return send_email_with_fallback(
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        from_email=from_email,
        from_name=from_name,
        to=[request_obj.email],
        reply_to=[from_email],
        extra_headers={"X-EMSArena-Trial-Request-ID": str(request_obj.pk)},
    )


def send_reply_to_trial_request(
    *,
    request_obj: TrialExamRequest,
    reply_body: str,
    reply_from: str,
    sent_by,
) -> bool:
    """Persist the reply, mark the request as ``added`` and dispatch the email.

    DB persistence is synchronous so the admin's work survives an SMTP
    failure; the email is sent in a daemon thread so the response is never
    blocked on the network. Returns ``True`` once the reply is *recorded*;
    actual delivery status is tracked on the row.
    """
    from django.utils import timezone

    if reply_from not in _REPLY_FROM_ADDRESSES:
        raise ValueError(f"Unknown reply_from inbox: {reply_from!r}")

    request_obj.reply_body = reply_body
    request_obj.reply_from = reply_from
    request_obj.reply_sent_by = sent_by
    request_obj.reply_delivery_status = TrialExamRequest.REPLY_DELIVERY_PENDING
    request_obj.reply_delivery_error = ""
    request_obj.reply_sent_at = None
    request_obj.status = TrialExamRequest.STATUS_ADDED
    request_obj.is_handled = False
    request_obj.handled_at = None
    request_obj.save(
        update_fields=[
            "reply_body",
            "reply_from",
            "reply_sent_by",
            "reply_delivery_status",
            "reply_delivery_error",
            "reply_sent_at",
            "status",
            "is_handled",
            "handled_at",
        ]
    )

    def _runner() -> None:
        try:
            ok, reason = _send_reply_email(request_obj, reply_body, reply_from)
            sent_at = timezone.now()
            if not ok:
                TrialExamRequest.objects.filter(pk=request_obj.pk).update(
                    reply_delivery_status=TrialExamRequest.REPLY_DELIVERY_FAILED,
                    reply_delivery_error=reason[:500],
                )
                logger.error(
                    "Trial reply email failed via SMTP and API: %s",
                    reason,
                    extra={"trial_request_id": request_obj.pk},
                )
                return
            TrialExamRequest.objects.filter(pk=request_obj.pk).update(
                reply_delivery_status=TrialExamRequest.REPLY_DELIVERY_SENT,
                reply_delivery_error="",
                reply_sent_at=sent_at,
                is_handled=True,
                handled_at=sent_at,
            )
        except Exception:
            logger.exception(
                "Trial reply background worker failed",
                extra={"trial_request_id": request_obj.pk},
            )

    threading.Thread(
        target=_runner,
        name=f"trial-reply-{request_obj.pk}",
        daemon=True,
    ).start()
    return True


# ---------------------------------------------------------------------------
# Public form entry point
# ---------------------------------------------------------------------------
def create_trial_exam_request(*, form, request) -> TrialExamRequest:
    """Persist a trial-exam request and trigger asynchronous notifications.

    ``form`` is a validated :class:`~apps.trial_exams.forms.TrialExamRequestForm`.
    The PDF keeps a randomised on-disk name; the original name is preserved on
    the row for display.
    """
    instance: TrialExamRequest = form.save(commit=False)

    uploaded = form.cleaned_data["questions_file"]
    instance.original_filename = (getattr(uploaded, "name", "") or "")[:255]
    randomize_uploaded_filename(uploaded)
    instance.questions_file = uploaded

    if request.user.is_authenticated:
        instance.user = request.user
    instance.ip_address = _extract_client_ip(request)
    instance.user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:512]
    instance.save()

    dispatch_trial_notifications(instance)
    return instance


def _extract_client_ip(request) -> str | None:
    """Return the originating client IP, honouring XFF where trusted."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        candidate = xff.split(",")[0].strip()
        if candidate:
            return candidate
    return request.META.get("REMOTE_ADDR")
