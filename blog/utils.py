import random
from django.conf import settings
from django.core.mail import send_mail
from django.core.signing import TimestampSigner

signer = TimestampSigner()

def generate_otp():
    return f"{random.randint(0, 999999):06d}"

def send_verify_email(user, code: str):
    token = signer.sign(str(user.pk))
    link = f"{settings.SITE_URL}/verify-email/?token={token}"

    subject = "Email təsdiqi"
    message = (
        f"Salam {user.username},\n\n"
        f"Təsdiq kodun: {code}\n"
        f"və ya linklə təsdiqlə: {link}\n\n"
        f"Kod 10 dəqiqə etibarlıdır."
    )

    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])
