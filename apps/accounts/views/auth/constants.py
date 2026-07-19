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
