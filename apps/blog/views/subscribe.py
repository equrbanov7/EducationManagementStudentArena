# blog/views/subscribe.py

import logging

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils.translation import pgettext

from ..forms import SubscriptionForm
from ..models import Subscriber

logger = logging.getLogger(__name__)


def subscribe_page(request):
    if request.method == "POST":
        form = SubscriptionForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]

            try:
                # 1. Abunəçini bazaya yaz
                subscriber, created = Subscriber.objects.get_or_create(email=email)

                if created or not subscriber.is_active:

                    # 2. Email şablonunu yarat
                    html_message = render_to_string("email_templates/welcome_email.html", {"email": email})

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
