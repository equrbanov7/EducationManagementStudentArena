# blog/views/subscribe.py

import logging

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils.translation import pgettext

from core.rate_limit import normalize_rate_identity, record_rate_limit_hit
from core.utils import get_client_ip

from ...forms import SubscriptionForm
from ...models import Subscriber

logger = logging.getLogger(__name__)
SUBSCRIBE_RATE_LIMIT_MESSAGE = "Çox sayda cəhd edildi. Zəhmət olmasa bir az sonra yenidən cəhd edin."
SUBSCRIBE_LIMIT_SCOPE_IP = "blog.subscribe.ip"
SUBSCRIBE_LIMIT_SCOPE_IDENTITY = "blog.subscribe.identity"


def _subscribe_limit_keys(request, email):
    client_ip = get_client_ip(request) or "unknown"
    normalized_email = normalize_rate_identity(email)
    return [
        (SUBSCRIBE_LIMIT_SCOPE_IP, client_ip),
        (SUBSCRIBE_LIMIT_SCOPE_IDENTITY, client_ip, normalized_email),
    ]


def subscribe_page(request):
    if request.method == "POST":
        form = SubscriptionForm(request.POST)
        raw_email = request.POST.get("email", "")

        for scope, *key_parts in _subscribe_limit_keys(request, raw_email):
            is_limited, retry_after = record_rate_limit_hit(scope, settings.SUBSCRIBE_RATE_LIMIT, *key_parts)
            if is_limited:
                messages.error(request, SUBSCRIBE_RATE_LIMIT_MESSAGE)
                response = render(request, "blog/subscribe.html", {"form": form}, status=429)
                if retry_after:
                    response.headers["Retry-After"] = str(retry_after)
                return response

        if form.is_valid():
            email = form.cleaned_data["email"]

            try:
                # 1. Abunəçini bazaya yaz
                subscriber, created = Subscriber.objects.get_or_create(email=email)

                if created or not subscriber.is_active:

                    # 2. Email şablonunu yarat
                    html_message = render_to_string(
                        "email_templates/welcome_email.html",
                        {
                            "email": email,
                            "brand": getattr(settings, "SITE_BRAND_NAME", "") or "EMSArena",
                        },
                    )

                    # 3. Email göndər
                    send_mail(
                        pgettext("blog.subscribe.email", "subject"),
                        pgettext("blog.subscribe.email", "plain_text_body").format(email=email),
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        html_message=html_message,
                        fail_silently=False,
                    )

                    messages.success(
                        request,
                        pgettext("blog.subscribe.message", "confirmation_email_sent").format(email=email),
                    )

                else:
                    messages.warning(
                        request, pgettext("blog.subscribe.message", "already_subscribed").format(email=email)
                    )

            except Exception:
                # Hər hansı bir xəta (məsələn, SMTP xətası) olarsa
                messages.error(
                    request,
                    pgettext("blog.subscribe.message", "send_error"),
                )
                logger.exception("Subscription email delivery failed")

            return redirect("subscribe")
        else:
            messages.error(request, pgettext("blog.subscribe.message", "invalid_email"))
    else:
        form = SubscriptionForm()

    return render(request, "blog/subscribe.html", {"form": form})
