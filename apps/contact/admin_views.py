"""Admin-only views for the Contact app.

The reply view is reachable only via the Django admin
(``admin:contact_contactmessage_reply``). Permission check enforces
``is_staff`` AND ``is_superuser`` — same gate the rest of the
ContactMessageAdmin uses for write actions.
"""

from __future__ import annotations

import logging

from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import ContactMessage
from .services import send_reply_to_contact

logger = logging.getLogger(__name__)


class ContactReplyForm(forms.Form):
    """Lightweight reply form. NOT a ModelForm because the reply fields
    on the model are updated by the service layer (which also handles
    the audit trail and email dispatch)."""

    reply_from = forms.ChoiceField(
        label=_("Hansı maildən cavab göndərilsin"),
        choices=ContactMessage.REPLY_FROM_CHOICES,
        initial="info",
    )
    reply_body = forms.CharField(
        label=_("Cavab mətni"),
        widget=forms.Textarea(attrs={"rows": 10, "style": "width:100%;"}),
        min_length=10,
        max_length=10000,
        help_text=_("Müştəriyə göndəriləcək cavab. Markdown dəstəklənmir; sadə mətn olaraq görünəcək."),
    )


@staff_member_required
@user_passes_test(lambda u: u.is_superuser)
def reply_to_contact_message(request: HttpRequest, pk: int) -> HttpResponse:
    """Render the reply form and process submissions.

    Only superusers can reply — this matches the read/delete permission
    on ContactMessageAdmin.
    """
    message = get_object_or_404(ContactMessage, pk=pk)

    if request.method == "POST":
        form = ContactReplyForm(request.POST)
        if form.is_valid():
            # Persists synchronously, dispatches email in a background
            # thread — the admin's HTTP response is returned immediately.
            send_reply_to_contact(
                message=message,
                reply_body=form.cleaned_data["reply_body"],
                reply_from=form.cleaned_data["reply_from"],
                sent_by=request.user,
            )
            messages.success(
                request,
                _("Cavab qeyd edildi və %(email)s ünvanına göndərilməyə çalışılır.") % {"email": message.email},
            )
            return redirect(reverse("admin:contact_contactmessage_change", args=[message.pk]))
    else:
        # Pre-fill subject based on the message subject category.
        initial_from = "support" if message.subject == "support" else "info"
        form = ContactReplyForm(initial={"reply_from": initial_from})

    context = {
        "title": _("Cavablandır: %(name)s") % {"name": message.name},
        "message": message,
        "form": form,
        "opts": ContactMessage._meta,
        "has_view_permission": True,
        "original": message,
    }
    return render(request, "admin/contact/contactmessage/reply.html", context)
