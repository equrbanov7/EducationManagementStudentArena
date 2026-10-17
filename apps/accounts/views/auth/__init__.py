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
from .logout import logout_view  # noqa: F401
from .profile_completion import complete_profile_view  # noqa: F401

__all__ = [
    "AUTH_DEVICE_COOKIE_NAME",
    "CustomLoginView",
    "complete_profile_view",
    "NamespacedPasswordResetConfirmView",
    "NamespacedPasswordResetDoneView",
    "NamespacedPasswordResetView",
    "login_portal",
    "logout_view",
    "set_initial_password_view",
]
