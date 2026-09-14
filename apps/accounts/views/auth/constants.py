"""accounts auth view paketi — constants."""

import logging
import re

from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


User = get_user_model()


AUTH_RATE_LIMIT_MESSAGE = "Çox sayda cəhd edildi. Zəhmət olmasa bir az sonra yenidən cəhd edin."


AUTH_DEVICE_COOKIE_NAME = "ems_auth_device"


AUTH_DEVICE_COOKIE_SALT = "accounts.auth_device"  # nosec B105 - signing salt, not a secret.


AUTH_DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


AUTH_DEVICE_ID_RE = re.compile(r"^[a-f0-9]{32,64}$")


LOGIN_LIMIT_SCOPE_DEVICE = "accounts.login.device"


LOGIN_LIMIT_SCOPE_IDENTITY = "accounts.login.identity"


# Superadmin qaçış yolunun ayrıca vedrəsi (2026-09-13 access auditi, F-01).
LOGIN_LIMIT_SCOPE_SUPERADMIN_ESCAPE = "accounts.login.superadmin_escape"


# İP-əsaslı OTP qapıları (2026-09-13 access auditi, F-09): göndəriş + yoxlama.
OTP_SEND_IP_LIMIT_SCOPE = "accounts.otp.ip.send"


OTP_VERIFY_IP_LIMIT_SCOPE = "accounts.otp.ip.verify"


# Kod-səviyyəli defaultlar: `config/settings/test.py` base-dən adları AÇIQ
# siyahı ilə idxal edir, ona görə yeni ayarlar orada görünməyə bilər —
# `getattr(settings, …, default)` ilə limit heç vaxt «yox» olmur (fail-closed
# ruhu, 2026-09-02 P2-5). Prod dəyəri `admin_ratelimit.py`-dədir.
LOGIN_SUPERADMIN_ESCAPE_RATE_LIMIT_DEFAULT = "3/1h"


OTP_SEND_IP_RATE_LIMIT_DEFAULT = "40/10m"


OTP_VERIFY_IP_RATE_LIMIT_DEFAULT = "100/10m"


def otp_send_ip_rate_limit():
    return getattr(settings, "OTP_SEND_IP_RATE_LIMIT", OTP_SEND_IP_RATE_LIMIT_DEFAULT)


def otp_verify_ip_rate_limit():
    return getattr(settings, "OTP_VERIFY_IP_RATE_LIMIT", OTP_VERIFY_IP_RATE_LIMIT_DEFAULT)


OTP_VERIFY_LIMIT_SCOPE = "accounts.otp.verify"


OTP_RESEND_LIMIT_SCOPE = "accounts.otp.resend"


AUTH_REDIRECT_MAX_LENGTH = 2048


AUTH_REDIRECT_DISALLOWED_CHARS = frozenset({"'", '"', "\\", "\r", "\n", "\t"})


PASSWORD_RESET_EMAIL_SESSION_KEY = "accounts_password_reset_email"


def _register_seo() -> dict:
    """Brand-driven SEO metadata for the signup page (no hard-coded product name)."""
    brand = getattr(settings, "SITE_BRAND_NAME", "") or "Qərbi Kaspi Universiteti"
    return {
        "seo_title": f"Hesab yaradın | {brand}",
        "seo_description": (
            f"{brand}-da təşkilat, müəllim və ya tələbə hesabı yaradın və " "rəqəmsal təhsil platformasına qoşulun."
        ),
    }
