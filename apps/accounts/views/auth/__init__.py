"""accounts auth — geriyə-uyğun fasad paketi."""

from .constants import (  # noqa: F401
    AUTH_DEVICE_COOKIE_NAME,
)
from .first_login import (  # noqa: F401
    set_initial_password_view,
)
from .login import (  # noqa: F401
    CustomLoginView,
    NamespacedPasswordResetConfirmView,
    NamespacedPasswordResetDoneView,
    NamespacedPasswordResetView,
    login_portal,
)
from .otp_api import (  # noqa: F401
    resend_otp_api_view,
    send_otp_api_view,
    verify_otp_api_view,
)
from .register import (  # noqa: F401
    logout_view,
    register_view,
    resend_code_view,
    verify_code_view,
    verify_email_link_view,
)

__all__ = [
    "AUTH_DEVICE_COOKIE_NAME",
    "CustomLoginView",
    "NamespacedPasswordResetConfirmView",
    "NamespacedPasswordResetDoneView",
    "NamespacedPasswordResetView",
    "login_portal",
    "logout_view",
    "register_view",
    "resend_code_view",
    "resend_otp_api_view",
    "send_otp_api_view",
    "set_initial_password_view",
    "verify_code_view",
    "verify_email_link_view",
    "verify_otp_api_view",
]
