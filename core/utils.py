"""
Core utility functions for EMS Arena project.
Reusable helper functions used across the application.
"""

import secrets
import string

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags


def generate_otp(length=6):
    """
    Generate a random OTP (One-Time Password) of specified length.
    """
    return "".join(secrets.choice(string.digits) for _ in range(length))


def generate_pin(length=4):
    """
    Generate a random PIN of specified length.
    """
    return "".join(secrets.choice(string.digits) for _ in range(length))


def generate_code(length=8):
    """
    Generate a random alphanumeric code of specified length.
    """
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def send_template_email(subject, template_name, context, recipient_list, from_email=None):
    """
    Send an email using a template.

    Args:
        subject: Email subject
        template_name: Path to email template
        context: Context dictionary for template rendering
        recipient_list: List of recipient email addresses
        from_email: Sender email (optional)
    """
    html_message = render_to_string(template_name, context)
    plain_message = strip_tags(html_message)

    send_mail(
        subject=subject,
        message=plain_message,
        from_email=from_email,
        recipient_list=recipient_list,
        html_message=html_message,
        fail_silently=False,
    )


def get_public_base_url(request=None):
    """
    Resolve the externally reachable site origin for links sent to users.
    """
    fallback_url = str(getattr(settings, "SITE_URL", "http://127.0.0.1:8000")).rstrip("/")
    if request is None:
        return fallback_url
    try:
        return request.build_absolute_uri("/").rstrip("/")
    except Exception:
        return fallback_url


def build_absolute_url(path="", request=None):
    """
    Build an absolute URL for a local path using the current request or SITE_URL.
    """
    if not path:
        return get_public_base_url(request)
    if str(path).startswith(("http://", "https://")):
        return str(path)
    normalized_path = str(path)
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    return f"{get_public_base_url(request)}{normalized_path}"


def get_auth_otp_expiry_seconds():
    """
    Return the configured OTP validity window in seconds.
    """
    return max(60, int(getattr(settings, "AUTH_OTP_EXPIRY_SECONDS", 300)))


def get_auth_otp_expiry_minutes():
    """
    Return the configured OTP validity window rounded up to minutes.
    """
    seconds = get_auth_otp_expiry_seconds()
    return max(1, (seconds + 59) // 60)


def get_auth_otp_resend_cooldown_seconds():
    """
    Return the minimum wait time before a new OTP can be resent.
    """
    return max(30, int(getattr(settings, "AUTH_OTP_RESEND_COOLDOWN_SECONDS", 60)))


def get_auth_otp_max_attempts():
    """
    Return the maximum allowed verification attempts per OTP.
    """
    return max(1, int(getattr(settings, "AUTH_OTP_MAX_ATTEMPTS", 5)))


def get_auth_otp_max_sends_per_hour():
    """
    Return the maximum number of OTP sends allowed per email per rolling hour.
    """
    return max(1, int(getattr(settings, "AUTH_OTP_MAX_SENDS_PER_HOUR", 5)))


def get_auth_pending_signup_ttl_seconds():
    """
    Return how long pending signup data may remain in server-side cache.
    """
    return max(get_auth_otp_expiry_seconds(), int(getattr(settings, "AUTH_PENDING_SIGNUP_TTL_SECONDS", 86400)))


def generate_unique_slug(model_class, title, slug_field="slug"):
    """
    Generate a unique slug for a model instance.

    Args:
        model_class: The model class to check uniqueness against
        title: The title/name to slugify
        slug_field: Name of the slug field (default: 'slug')

    Returns:
        A unique slug string
    """
    from django.utils.text import slugify

    base_slug = slugify(title)
    slug = base_slug
    counter = 1

    # Check if slug exists
    filter_kwargs = {slug_field: slug}
    while model_class.objects.filter(**filter_kwargs).exists():
        slug = f"{base_slug}-{counter}"
        filter_kwargs = {slug_field: slug}
        counter += 1

    return slug


#: Neçə ETİBARLI proxy sorğunu ötürür (kənardan içəri).  Bizim edge nginx
#: ``X-Forwarded-For``-u OVERWRITE edir (``docker/nginx/nginx.conf``), yəni bir
#: hop var və doğru üzv SONUNCU-dur.  Cloudflare kimi əlavə bir qat qoşulsa
#: ``TRUSTED_PROXY_HOPS=2`` verilir.
_DEFAULT_TRUSTED_PROXY_HOPS = 1


def get_client_ip(request):
    """Sorğunun müştəri IP-si — ETİBARLI PROXY semantikası ilə (SAĞDAN).

    ⚠️ 2026-09-02 audit, P2-6: bu funksiya ƏVVƏL ``X-Forwarded-For``-un ƏN SOL
    üzvünü götürürdü.  Həmin üzvü tamamilə MÜŞTƏRİ yazır — yəni istənilən şəxs
    ``X-Forwarded-For: 1.2.3.4`` göndərib per-IP limitləri (login, OTP, contact)
    və IP-əsaslı qapıları saxtalaşdıra bilirdi.  Layihədə eyni başlıq beş yerdə
    müstəqil parse olunurdu; ikisi (monitoring) düzgün — SAĞDAN — oxuyurdu.

    İndi TƏK mənbə budur: sağdan ``TRUSTED_PROXY_HOPS`` sayda üzv atılır və
    qalanın sonuncusu götürülür.  Başlıq yoxdursa ``REMOTE_ADDR``.

    Qaytarır: ``str`` və ya ``None`` (köhnə müqavilə saxlanılır — çağıranlar öz
    fallback-larını tətbiq edir, nullable ``GenericIPAddressField``-lər üçün).
    """
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")
    members = [part.strip() for part in forwarded if part.strip()]
    if members:
        try:
            hops = int(getattr(settings, "TRUSTED_PROXY_HOPS", _DEFAULT_TRUSTED_PROXY_HOPS) or 1)
        except (TypeError, ValueError):
            hops = _DEFAULT_TRUSTED_PROXY_HOPS
        hops = max(1, hops)
        # hops=1 → sonuncu üzv; hops=2 → sondan ikinci; siyahı qısadırsa ən sol.
        return members[max(0, len(members) - hops)]
    return request.META.get("REMOTE_ADDR")
