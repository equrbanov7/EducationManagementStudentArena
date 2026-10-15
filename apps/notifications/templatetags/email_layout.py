"""E-poçt şablonlarının vahid «çərçivəsi» üçün template tag-lar (2026-10-15).

Sahib: «Mailə gələn template-in dizaynını yaxşılaşdır.» Bütün məktublar
``templates/emails/base_email.html`` / ``base_email.txt``-dən törəyir. Məktublar
``render_to_string`` ilə **request context processor-ları olmadan** render olunur,
ona görə başlıq/altlıq üçün lazım olan sabit məlumat (universitetin adı, mütləq
logo ünvanı, dəstək ünvanı) göndərənlərin kontekstinə toxunmadan buradan gəlir.

İstifadə::

    {% load email_layout %}
    {% email_chrome as chrome %}
    {{ chrome.brand }} · {{ chrome.product }} · {{ chrome.support_email }}
    <a href="{{ post.get_absolute_url|email_absolute_url }}">…</a>
"""

from __future__ import annotations

import ipaddress
import logging
from urllib.parse import urlsplit

from django import template
from django.conf import settings
from django.templatetags.static import static

logger = logging.getLogger(__name__)

register = template.Library()

DEFAULT_BRAND = "Qərbi Kaspi Universiteti"
PRODUCT_NAME = "EMS Arena"
#: Kvadrat işarə — başlıq zolağında 40×40 göstərilir (429×429 PNG, şəffaf fon).
LOGO_STATIC_PATH = "brand/logo-mark.png"


def _site_url() -> str:
    value = str(getattr(settings, "SITE_URL", "") or "").strip().rstrip("/")
    return value if value.startswith(("http://", "https://")) else ""


def _host_is_public(site_url: str) -> bool:
    """Logo yalnız poçt klientinin çata biləcəyi ünvandan verilir: HTTPS + IP/localhost olmayan host."""
    parts = urlsplit(site_url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or host == "localhost" or host.endswith((".local", ".localhost", ".test")):
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True
    return False


def _logo_url(site_url: str) -> str:
    if not site_url or not _host_is_public(site_url):
        return ""
    try:
        path = static(LOGO_STATIC_PATH)
    except Exception:  # manifest-də yoxdursa məktub logosuz gedir
        logger.warning("email logo static path could not be resolved: %s", LOGO_STATIC_PATH)
        return ""
    if path.startswith(("http://", "https://")):
        return path
    return f"{site_url}/{path.lstrip('/')}"


def _support_email() -> str:
    value = str(getattr(settings, "CONTACT_SUPPORT_EMAIL", "") or "").strip()
    return value if "@" in value else ""


@register.simple_tag
def email_chrome() -> dict:
    """Başlıq/altlıq məlumatı: brend, məhsul adı, sayt, logo və dəstək ünvanı."""
    site_url = _site_url()
    return {
        "brand": getattr(settings, "SITE_BRAND_NAME", "") or DEFAULT_BRAND,
        "product": PRODUCT_NAME,
        "site_url": site_url,
        "logo_url": _logo_url(site_url),
        "support_email": _support_email(),
    }


@register.filter
def email_absolute_url(value) -> str:
    """Nisbi yolu (``/blog/x/``) ``SITE_URL`` ilə mütləq linkə çevirir; mütləq link olduğu kimi qalır."""
    text = str(value or "").strip()
    if not text or text.startswith(("http://", "https://", "mailto:")):
        return text
    site_url = _site_url()
    if not site_url:
        return text
    return f"{site_url}/{text.lstrip('/')}"
