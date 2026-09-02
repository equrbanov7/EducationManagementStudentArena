"""Public contact page view.

Rate limiting strategy
----------------------
Two layers protect the endpoint:

1. **Per-IP**: ``CONTACT_IP_RATE`` submissions per minute. Stops a
   single-source flood quickly.
2. **Per-Email**: ``CONTACT_EMAIL_RATE`` submissions per hour. Stops a
   bot that rotates IPs but reuses a sender address.

Both use the cache-backed helpers from ``core.rate_limit`` so behaviour
is consistent with login / OTP / register endpoints.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.rate_limit import record_rate_limit_hit

from .forms import ContactForm
from .services import create_contact_message

logger = logging.getLogger(__name__)

CONTACT_IP_RATE = "5/m"
CONTACT_EMAIL_RATE = "10/h"


def _client_ip(request: HttpRequest) -> str:
    """Vahid ``core.utils.get_client_ip`` helperinə həvalə (2026-09-02 audit, P2-6).

    Başlıq layihədə beş yerdə müstəqil parse olunurdu; ikisi soldan (saxta
    edilə bilən) oxuyurdu.  Artıq TƏK mənbə var: etibarlı proxy semantikası
    (sağdan ``TRUSTED_PROXY_HOPS``).
    """
    from core.utils import get_client_ip

    return get_client_ip(request) or "unknown"


@never_cache
@require_http_methods(["GET", "POST"])
def contact_page(request: HttpRequest) -> HttpResponse:
    """Render the contact page and process submissions."""
    brand = getattr(settings, "SITE_BRAND_NAME", "") or "Qərbi Kaspi Universiteti"
    seo_context = {
        "seo_title": _("Əlaqə – %(brand)s") % {"brand": brand},
        "seo_description": _(
            "%(brand)s ilə əlaqə saxlayın. Suallarınız, təklifləriniz və əməkdaşlıq istəkləriniz üçün bizə yazın."
        )
        % {"brand": brand},
        "seo_breadcrumbs": [
            {"name": _("Ana səhifə"), "url": request.build_absolute_uri("/")},
            {"name": _("Əlaqə"), "url": request.build_absolute_uri()},
        ],
    }

    if request.method == "POST":
        # ---- IP-based rate limit ----
        ip = _client_ip(request)
        limited, retry = record_rate_limit_hit("contact_ip", CONTACT_IP_RATE, ip)
        if limited:
            messages.error(
                request,
                _("Çox sayda mesaj göndərilib. Zəhmət olmasa bir az gözləyin."),
            )
            return render(
                request,
                "contact/contact.html",
                {"form": ContactForm(), **seo_context, "rate_limited": True},
                status=429,
            )

        form = ContactForm(request.POST)
        if form.is_valid():
            # ---- Email-based rate limit (only after format validation) ----
            email = form.cleaned_data["email"].lower()
            limited, _retry = record_rate_limit_hit("contact_email", CONTACT_EMAIL_RATE, email)
            if limited:
                messages.error(
                    request,
                    _("Bu email ünvanından çox sayda mesaj göndərilib. Sabah yenidən cəhd edin."),
                )
                return render(
                    request,
                    "contact/contact.html",
                    {"form": form, **seo_context, "rate_limited": True},
                    status=429,
                )

            try:
                # Persists synchronously and dispatches email in a daemon
                # thread — the HTTP response is no longer blocked by SMTP I/O.
                create_contact_message(form_cleaned_data=form.cleaned_data, request=request)
            except Exception:
                # Only DB-level failures land here; SMTP errors are caught
                # inside the background thread and never surface to the user.
                logger.exception("Contact submission failed during DB persistence")
                messages.error(
                    request,
                    _("Mesajınızı qəbul edə bilmədik. Zəhmət olmasa daha sonra cəhd edin."),
                )
                return render(
                    request,
                    "contact/contact.html",
                    {"form": form, **seo_context},
                    status=500,
                )

            messages.success(
                request,
                _("Mesajınız uğurla qəbul edildi. Tezliklə sizinlə əlaqə saxlayacağıq."),
            )
            return redirect(reverse("contact") + "?sent=1")
    else:
        form = ContactForm()

    context = {
        "form": form,
        "submitted": request.GET.get("sent") == "1",
        **seo_context,
    }
    return render(request, "contact/contact.html", context)
