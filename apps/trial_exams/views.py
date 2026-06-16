"""Student-facing trial-exam request view.

Access
------
Login is required (decided product-side: only authenticated students may
request a free trial exam). Name/email are pre-filled from the user but the
student can edit them.

Rate limiting
-------------
Mirrors the contact endpoint via ``core.rate_limit``:
* Per-IP: stops a single-source flood.
* Per-user: stops one account from spamming uploads.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.rate_limit import record_rate_limit_hit

from .forms import TrialExamRequestForm
from .services import create_trial_exam_request

logger = logging.getLogger(__name__)

TRIAL_IP_RATE = "5/m"
TRIAL_USER_RATE = "8/h"


def _client_ip(request: HttpRequest) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or "unknown"


def _initial_from_user(request: HttpRequest) -> dict:
    user = request.user
    full_name = (user.get_full_name() or "").strip() or user.username
    return {"full_name": full_name, "email": user.email or ""}


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def trial_exam_request_page(request: HttpRequest) -> HttpResponse:
    """Render the trial-exam request page and process submissions."""
    seo_context = {
        "seo_title": _("Sınaq imtahanı – EMSArena"),
        "seo_description": _(
            "Pulsuz və limitsiz sınaq imtahanı yarat: suallarını PDF formatında "
            "yüklə, komandamız gün ərzində sistemə əlavə etsin."
        ),
    }

    if request.method == "POST":
        # ---- IP-based rate limit ----
        ip = _client_ip(request)
        limited, _retry = record_rate_limit_hit("trial_ip", TRIAL_IP_RATE, ip)
        if limited:
            messages.error(request, _("Çox sayda sorğu göndərilib. Zəhmət olmasa bir az gözləyin."))
            return render(
                request,
                "trial_exams/trial_exam_request.html",
                {"form": TrialExamRequestForm(initial=_initial_from_user(request)), **seo_context},
                status=429,
            )

        # ---- Per-user rate limit ----
        limited, _retry = record_rate_limit_hit("trial_user", TRIAL_USER_RATE, str(request.user.pk))
        if limited:
            messages.error(request, _("Bu gün üçün sorğu limitinə çatdınız. Sabah yenidən cəhd edin."))
            return render(
                request,
                "trial_exams/trial_exam_request.html",
                {"form": TrialExamRequestForm(initial=_initial_from_user(request)), **seo_context},
                status=429,
            )

        form = TrialExamRequestForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                create_trial_exam_request(form=form, request=request)
            except Exception:
                logger.exception("Trial request failed during DB persistence")
                messages.error(request, _("Sorğunuzu qəbul edə bilmədik. Zəhmət olmasa daha sonra cəhd edin."))
                return render(
                    request,
                    "trial_exams/trial_exam_request.html",
                    {"form": form, **seo_context},
                    status=500,
                )

            messages.success(request, _("Sorğunuz qəbul edildi! Suallar gün ərzində sistemə əlavə olunacaq."))
            return redirect(reverse("trial_exams:request") + "?sent=1")
    else:
        form = TrialExamRequestForm(initial=_initial_from_user(request))

    context = {
        "form": form,
        "submitted": request.GET.get("sent") == "1",
        **seo_context,
    }
    return render(request, "trial_exams/trial_exam_request.html", context)
