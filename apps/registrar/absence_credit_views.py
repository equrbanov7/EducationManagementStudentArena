"""Mövcud journal.correct qapısında ümumi saat düzəlişi və geri alma."""

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from . import absence_credit, corrections
from .journal_access import offering_or_404, writable_offering_or_404
from .models import AbsenceCredit, Enrollment


@login_required
@require_POST
def apply(request, offering_id):
    if not corrections.can_correct_journal(request):
        raise Http404
    offering = writable_offering_or_404(offering_or_404(request, offering_id))
    try:
        entry = absence_credit.adjust(
            request=request,
            offering=offering,
            enrollment_id=request.POST.get("enrollment"),
            hours=request.POST.get("hours"),
            reason=request.POST.get("reason"),
            request_token=request.POST.get("request_token"),
            reverses_id=request.POST.get("reverses"),
        )
    except (ValidationError, PermissionError) as exc:
        message = (
            "; ".join(exc.messages)
            if isinstance(exc, ValidationError)
            else pgettext("registrar.absence_credit", "Düzəlişə icazə yoxdur.")
        )
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {"ok": False, "error": message}, status=409 if isinstance(exc, absence_credit.CreditConflict) else 400
            )
        messages.error(request, message)
    else:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "ok": True,
                    "id": str(entry.pk),
                    "absence_hours": Enrollment.objects.get(pk=entry.enrollment_id).absence_hours,
                }
            )
        messages.success(request, pgettext("registrar.absence_credit", "Ümumi üzrlü qayıb saatı yadda saxlanıldı."))
    return redirect(reverse("registrar:journal_detail", args=[offering.pk]) + "?correct=1")


def context(offering):
    entries = list(
        AbsenceCredit.objects.filter(enrollment__offering=offering, organization=offering.organization)
        .select_related("enrollment__student", "actor", "reversed_by")
        .order_by("-created_at")
    )
    for entry in entries:
        entry.reversal_token = uuid.uuid4()
    return {"absence_credit_entries": entries, "absence_credit_token": uuid.uuid4()}
