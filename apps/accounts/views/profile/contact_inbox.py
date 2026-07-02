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
from apps.contact.public import send_reply_to_contact
from apps.trial_exams.models import TrialExamRequest
from apps.trial_exams.public import send_reply_to_trial_request

logger = logging.getLogger(__name__)

CONTACT_LIST_LIMIT = 50
CONTACT_SIDEBAR_BADGE_LIMIT = 99  # cap so the badge stays compact

_DEFAULT_TRIAL_REPLY = _(
    "Salam! Göndərdiyiniz suallar əsasında sınaq imtahanınız EMSArena sistemində "
    "yaradıldı. Hesabınıza daxil olub “İmtahanlar” bölməsindən imtahanı pulsuz və "
    "limitsiz şəkildə verə bilərsiniz. Uğurlar!"
)


def _can_access_contact_inbox(capabilities: dict) -> bool:
    """Single source of truth for the access gate."""
    return bool(capabilities.get("is_superadmin")) and (
        "superadmin-contact-messages" in capabilities.get("allowed_sections", set())
    )


def _contact_status(message: ContactMessage) -> str:
    if message.reply_delivery_status in {
        ContactMessage.REPLY_DELIVERY_SENT,
        ContactMessage.REPLY_DELIVERY_PENDING,
        ContactMessage.REPLY_DELIVERY_FAILED,
        ContactMessage.REPLY_DELIVERY_RECORDED,
    }:
        return message.reply_delivery_status
    return "recorded" if message.is_handled else "new"


def _trial_status(request_obj: TrialExamRequest) -> str:
    if request_obj.reply_delivery_status in {
        TrialExamRequest.REPLY_DELIVERY_SENT,
        TrialExamRequest.REPLY_DELIVERY_PENDING,
        TrialExamRequest.REPLY_DELIVERY_FAILED,
        TrialExamRequest.REPLY_DELIVERY_RECORDED,
    }:
        return request_obj.reply_delivery_status
    return "recorded" if request_obj.is_handled else "new"


def _contact_item(message: ContactMessage) -> dict:
    return {
        "kind": "contact",
        "pk": message.pk,
        "name": message.name,
        "email": message.email,
        "created_at": message.created_at,
        "subject": message.get_subject_display(),
        "snippet": message.message,
        "status": _contact_status(message),
        "has_attachment": False,
        "object": message,
    }


def _trial_item(request_obj: TrialExamRequest) -> dict:
    return {
        "kind": "trial",
        "pk": request_obj.pk,
        "name": request_obj.full_name,
        "email": request_obj.email,
        "created_at": request_obj.created_at,
        "subject": _("Sınaq imtahanı: %(subject)s") % {"subject": request_obj.subject_name},
        "snippet": request_obj.note or request_obj.original_filename or request_obj.subject_name,
        "status": _trial_status(request_obj),
        "has_attachment": bool(request_obj.questions_file),
        "object": request_obj,
    }


def _unhandled_count() -> int:
    return (
        ContactMessage.objects.filter(is_handled=False).count()
        + TrialExamRequest.objects.filter(is_handled=False).count()
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

    ctx: dict = {"contact_unhandled_count": min(_unhandled_count(), CONTACT_SIDEBAR_BADGE_LIMIT)}

    if active_section != "superadmin-contact-messages":
        return ctx

    contact_qs = ContactMessage.objects.all().select_related("reply_sent_by")
    trial_qs = TrialExamRequest.objects.all().select_related("reply_sent_by", "user")
    search_query = (request.GET.get("q") or "").strip()[:200]
    if search_query:
        contact_qs = contact_qs.filter(
            Q(name__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(message__icontains=search_query)
            | Q(reply_body__icontains=search_query)
        )
        trial_qs = trial_qs.filter(
            Q(full_name__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(subject_name__icontains=search_query)
            | Q(note__icontains=search_query)
            | Q(original_filename__icontains=search_query)
            | Q(reply_body__icontains=search_query)
        )

    contact_items = [_contact_item(item) for item in contact_qs.order_by("-created_at")[:CONTACT_LIST_LIMIT]]
    trial_items = [_trial_item(item) for item in trial_qs.order_by("-created_at")[:CONTACT_LIST_LIMIT]]
    inbox_items = sorted(
        [*contact_items, *trial_items],
        key=lambda item: item["created_at"],
        reverse=True,
    )[:CONTACT_LIST_LIMIT]

    ctx.update(
        {
            "contact_messages_list": inbox_items,
            "contact_total_count": ContactMessage.objects.count() + TrialExamRequest.objects.count(),
            "contact_replied_count": ContactMessage.objects.filter(
                reply_delivery_status=ContactMessage.REPLY_DELIVERY_SENT
            ).count()
            + TrialExamRequest.objects.filter(reply_delivery_status=TrialExamRequest.REPLY_DELIVERY_SENT).count(),
            "contact_failed_count": ContactMessage.objects.filter(
                reply_delivery_status=ContactMessage.REPLY_DELIVERY_FAILED
            ).count()
            + TrialExamRequest.objects.filter(reply_delivery_status=TrialExamRequest.REPLY_DELIVERY_FAILED).count(),
            "contact_pending_count": ContactMessage.objects.filter(
                reply_delivery_status=ContactMessage.REPLY_DELIVERY_PENDING
            ).count()
            + TrialExamRequest.objects.filter(reply_delivery_status=TrialExamRequest.REPLY_DELIVERY_PENDING).count(),
            "contact_recorded_count": ContactMessage.objects.filter(
                reply_delivery_status=ContactMessage.REPLY_DELIVERY_RECORDED
            ).count()
            + TrialExamRequest.objects.filter(reply_delivery_status=TrialExamRequest.REPLY_DELIVERY_RECORDED).count(),
            "contact_search_query": search_query,
            "default_trial_reply": _DEFAULT_TRIAL_REPLY,
        }
    )

    # Detail view (one message/request + reply form).
    message_id = (request.GET.get("message_id") or "").strip()
    if message_id.isdigit():
        selected = ContactMessage.objects.filter(pk=int(message_id)).first()
        if selected is not None:
            ctx["contact_selected_message"] = selected

    trial_id = (request.GET.get("trial_id") or "").strip()
    if trial_id.isdigit():
        selected_trial = TrialExamRequest.objects.filter(pk=int(trial_id)).first()
        if selected_trial is not None:
            ctx["trial_selected_request"] = selected_trial

    return ctx


def handle_contact_reply_post(
    request: HttpRequest,
    *,
    capabilities: dict,
) -> "HttpResponse | None":
    """Handle the inline reply POST. Returns a redirect on success/error,
    or None if this POST is not addressed to the contact inbox."""
    action = request.POST.get("action")
    if action not in {"contact_reply", "trial_reply"}:
        return None

    if not _can_access_contact_inbox(capabilities):
        django_messages.error(request, _("Bu əməliyyat üçün icazəniz yoxdur."))
        return redirect(reverse("accounts:profile"))

    if action == "trial_reply":
        return _handle_trial_reply_post(request)
    return _handle_contact_reply_post(request)


def _handle_contact_reply_post(request: HttpRequest) -> HttpResponse:
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


def _handle_trial_reply_post(request: HttpRequest) -> HttpResponse:
    trial_id = (request.POST.get("trial_id") or "").strip()
    if not trial_id.isdigit():
        django_messages.error(request, _("Sınaq imtahanı sorğusu tapılmadı."))
        return redirect(reverse("accounts:profile") + "?section=superadmin-contact-messages")

    trial_request = TrialExamRequest.objects.filter(pk=int(trial_id)).first()
    if trial_request is None:
        django_messages.error(request, _("Sınaq imtahanı sorğusu tapılmadı."))
        return redirect(reverse("accounts:profile") + "?section=superadmin-contact-messages")

    reply_body = (request.POST.get("reply_body") or "").strip()
    reply_from = (request.POST.get("reply_from") or "info").strip()
    detail_url = f"{reverse('accounts:profile')}?section=superadmin-contact-messages&trial_id={trial_request.pk}"

    if len(reply_body) < 10:
        django_messages.error(request, _("Cavab mətni ən azı 10 simvol olmalıdır."))
        return redirect(detail_url)
    if len(reply_body) > 10000:
        django_messages.error(request, _("Cavab mətni 10000 simvoldan uzun ola bilməz."))
        return redirect(detail_url)
    if reply_from not in {"info", "support"}:
        django_messages.error(request, _("Yanlış göndərən ünvanı."))
        return redirect(detail_url)

    send_reply_to_trial_request(
        request_obj=trial_request,
        reply_body=reply_body,
        reply_from=reply_from,
        sent_by=request.user,
    )
    django_messages.success(
        request,
        _("Təsdiq qeyd edildi və %(email)s ünvanına göndərilməyə çalışılır.") % {"email": trial_request.email},
    )
    return redirect(detail_url)
