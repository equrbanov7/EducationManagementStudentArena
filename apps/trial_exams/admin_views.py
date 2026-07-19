"""Admin-only reply view for trial-exam requests.

Reachable only via the Django admin
(``admin:trial_exams_trialexamrequest_reply``). The permission check enforces
``is_staff`` AND ``is_superuser`` — the same gate the rest of
``TrialExamRequestAdmin`` uses for write actions.

Sending a reply means "the questions have been added"; the service layer
flips the request status to ``added`` and dispatches the confirmation email.
"""

from __future__ import annotations

import logging

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import TrialExamRequest
from .services import send_reply_to_trial_request

logger = logging.getLogger(__name__)

_DEFAULT_REPLY_TEMPLATE = _(
    "Salam! Göndərdiyiniz suallar əsasında sınaq imtahanınız %(brand)s sistemində "
    "yaradıldı. Hesabınıza daxil olub “İmtahanlar” bölməsindən imtahanı pulsuz və "
    "limitsiz şəkildə verə bilərsiniz. Uğurlar!"
)


def _default_reply_text() -> str:
    """Render ``_DEFAULT_REPLY_TEMPLATE`` with the active tenant brand."""
    brand = getattr(settings, "SITE_BRAND_NAME", "") or "Qərbi Kaspi Universiteti"
    return _DEFAULT_REPLY_TEMPLATE % {"brand": brand}


class TrialReplyForm(forms.Form):
    """Lightweight reply form. NOT a ModelForm — the reply fields on the model
    are updated by the service layer (audit trail + email dispatch)."""

    reply_from = forms.ChoiceField(
        label=_("Hansı maildən cavab göndərilsin"),
        choices=TrialExamRequest.REPLY_FROM_CHOICES,
        initial="info",
    )
    reply_body = forms.CharField(
        label=_("Cavab mətni"),
        widget=forms.Textarea(attrs={"rows": 10, "style": "width:100%;"}),
        min_length=10,
        max_length=10000,
        initial=_default_reply_text,
        help_text=_("Tələbəyə göndəriləcək təsdiq. Sadə mətn olaraq görünəcək."),
    )


@staff_member_required
@user_passes_test(lambda u: u.is_superuser)
def reply_to_trial_request(request: HttpRequest, pk: int) -> HttpResponse:
    """Render the reply form and process submissions (superusers only)."""
    obj = get_object_or_404(TrialExamRequest, pk=pk)

    if request.method == "POST":
        form = TrialReplyForm(request.POST)
        if form.is_valid():
            send_reply_to_trial_request(
                request_obj=obj,
                reply_body=form.cleaned_data["reply_body"],
                reply_from=form.cleaned_data["reply_from"],
                sent_by=request.user,
            )
            messages.success(
                request,
                _("Təsdiq göndərilir və sorğu “sistemə əlavə olundu” kimi işarələndi."),
            )
            return redirect(reverse("admin:trial_exams_trialexamrequest_change", args=[obj.pk]))
    else:
        form = TrialReplyForm()

    context = {
        "title": _("Tələbəyə cavab"),
        "trial_request": obj,
        "form": form,
        "opts": TrialExamRequest._meta,
    }
    return render(request, "admin/trial_exams/trialexamrequest/reply.html", context)
