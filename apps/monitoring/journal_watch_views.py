"""Request boundaries for the RİM journal-watch panel and mailbox ownership confirmation."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods, require_POST

from . import journal_watch_config as service


@login_required
@never_cache
@require_POST
def people(request):
    try:
        rows = service.search_people(request, request.POST.get("kind", ""), request.POST.get("q", "")[:80])
    except ValidationError as exc:
        return JsonResponse({"error": " ".join(exc.messages)}, status=400)
    return JsonResponse({"people": rows})


@login_required
@never_cache
@require_POST
def configure(request):
    action = request.POST.get("action")
    try:
        if action == "recipient":
            service.request_recipient(request=request, email=request.POST.get("email", ""))
            messages.success(request, _("Təsdiq məktubu üçün sorğu qeydə alındı."))
        elif action == "remove_recipient":
            service.delete_recipient(request=request, recipient_id=request.POST.get("recipient_id"))
            messages.success(request, _("Bildiriş ünvanı siyahıdan çıxarıldı."))
        elif action == "save":
            service.save_watch(
                request=request,
                person_id=request.POST.get("person"),
                person_kind=request.POST.get("kind"),
                events=request.POST.getlist("events"),
                recipient_ids=request.POST.getlist("recipients"),
                watch_id=request.POST.get("watch_id") or None,
                active=request.POST.get("active") == "on",
            )
            messages.success(request, _("Nəzarət qaydası saxlanıldı."))
        elif action == "remove":
            service.delete_watch(request=request, watch_id=request.POST.get("watch_id"))
            messages.success(request, _("Nəzarət qaydası silindi."))
        else:
            return HttpResponseBadRequest()
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(reverse("accounts:profile") + "?section=journal-watch")


@never_cache
@sensitive_post_parameters("token")
@require_http_methods(["GET", "POST"])
def confirm(request):
    status = 200
    outcome = ""
    if request.method == "POST":
        try:
            service.confirm_recipient(token=request.POST.get("token", "")[:1024])
            outcome = _("E-poçt ünvanı təsdiqləndi.")
        except ValidationError as exc:
            outcome = " ".join(exc.messages)
            status = 400
    response = render(request, "monitoring/journal_watch/confirm.html", {"outcome": outcome}, status=status)
    response["Referrer-Policy"] = "same-origin"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response
