import base64
import random
import re
from django.conf import settings
from django.core.mail import send_mail
from django.core.signing import TimestampSigner
from django.utils import timezone
from django.core.files.base import ContentFile


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



DATA_URL_PNG_RE = re.compile(r"^data:image\/png;base64,(.+)$")

def _save_paint_png_to_answer(ans, data_url: str):
    """
    data_url format: data:image/png;base64,....
    """
    if not data_url:
        return False

    m = DATA_URL_PNG_RE.match((data_url or "").strip())
    if not m:
        return False

    b64_data = m.group(1)

    # çox böyük payload-ları blokla (təhlükəsizlik)
    if len(b64_data) > 3_500_000:  # ~2.6MB binary civarı
        return False

    try:
        binary = base64.b64decode(b64_data)
    except Exception:
        return False

    filename = f"paint_answer_{ans.id}.png"
    ans.paint_image.save(filename, ContentFile(binary), save=False)
    ans.paint_updated_at = timezone.now()
    ans.has_paint = True
    return True

def _clear_paint_from_answer(ans):
    """
    həm file-i silir, həm field-i null edir
    """
    if ans.paint_image:
        ans.paint_image.delete(save=False)
    ans.paint_image = None
    ans.has_paint = False
    ans.paint_updated_at = timezone.now()