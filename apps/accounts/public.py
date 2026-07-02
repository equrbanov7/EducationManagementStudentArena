"""accounts modulunun PUBLIC API fasadı (M3-B, 2026-07-02).

Rol sabitləri/pure helper-lər core.roles-dadır; admin OTP hook-ları
core.auth_otp-dadır. Genişlənmə nöqtəsi: apps.accounts.profile_hooks
(profil bölmə kontribusiyaları — blog ready()-də qeydiyyat).
"""

from apps.accounts.services import (  # noqa: F401
    issue_email_otp,
    purge_stale_pending_registration,
    verify_otp_code,
)
from core.roles import (  # noqa: F401
    ProfileRole,
    get_user_role_level,
    is_superadmin_user,
    map_org_role_to_profile_role,
    user_has_any_role,
)

__all__ = [
    "ProfileRole",
    "get_user_role_level",
    "is_superadmin_user",
    "issue_email_otp",
    "map_org_role_to_profile_role",
    "purge_stale_pending_registration",
    "user_has_any_role",
    "verify_otp_code",
]
