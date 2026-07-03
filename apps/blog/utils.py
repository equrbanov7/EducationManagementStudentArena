import secrets

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.signing import TimestampSigner
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import pgettext

from core.utils import build_absolute_url, get_auth_otp_expiry_minutes

signer = TimestampSigner()


def generate_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


def send_verify_email(user, code: str, *, request=None, expires_at=None):
    token = signer.sign(str(user.pk))
    verification_url = build_absolute_url(reverse("accounts:verify_email_link"), request=request)
    link = f"{verification_url}?token={token}"

    subject = pgettext("accounts.email.subject", "Email təsdiqi")
    context = {
        "user": user,
        "code": code,
        "verification_link": link,
        "otp_expiry_minutes": get_auth_otp_expiry_minutes(),
        "expires_at": expires_at,
    }
    text_body = render_to_string("accounts/emails/verification_email.txt", context)
    html_body = render_to_string("accounts/emails/verification_email.html", context)

    message = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [user.email])
    message.attach_alternative(html_body, "text/html")
    message.send()


# M2 (2026-07-02): tərif core-a köçüb; import səthi qorunur (AGENTS §1).
from core.constants import DATA_URL_PNG_RE  # noqa: F401,E402
