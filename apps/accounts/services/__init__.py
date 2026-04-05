"""
Accounts service layer.

The accounts app now exposes explicit ``policies``, ``queries``, and ``services``
packages. This module re-exports the previous ``apps.accounts.services`` public
API so existing imports continue to work.
"""

from ..policies import (
    get_profile_role_label,
    get_user_role_level,
    is_superadmin_user,
    map_org_role_to_profile_role,
    map_signup_role_to_profile_role,
    permission_is_grantable,
    resolve_membership_role,
    user_has_any_role,
)
from ..queries import (
    get_assigned_courses_for_user,
    get_assigned_exams_for_user,
    get_course_membership_groups,
    get_latest_pending_otp,
    get_signup_lookup_payload,
    pending_student_request_queryset,
)
from .auth import (
    OTPRateLimitError,
    OTPResendCooldownError,
    activate_user_account,
    get_otp_timer_context,
    issue_email_otp,
    send_login_otp,
    send_otp_email,
    send_verification_otp,
    verify_email_otp,
    verify_otp_code,
)
from .organization_requests import (
    activate_verified_membership,
    activate_verified_student_membership,
    close_other_pending_student_requests,
    set_student_org_request_status,
    sync_profile_pending_request_snapshot,
)
from .pending_registration import (
    PendingRegistrationError,
    PendingRegistrationNotFound,
    clear_pending_registration,
    finalize_pending_registration,
    get_pending_registration,
    store_pending_registration,
)
from .parsing import parse_decimal_score
from .profile import update_user_profile, update_user_role
from .registration import create_user_with_organization, purge_stale_pending_registration

__all__ = [
    "activate_user_account",
    "OTPRateLimitError",
    "OTPResendCooldownError",
    "activate_verified_membership",
    "activate_verified_student_membership",
    "PendingRegistrationError",
    "PendingRegistrationNotFound",
    "clear_pending_registration",
    "close_other_pending_student_requests",
    "create_user_with_organization",
    "finalize_pending_registration",
    "get_pending_registration",
    "purge_stale_pending_registration",
    "get_assigned_courses_for_user",
    "get_assigned_exams_for_user",
    "get_course_membership_groups",
    "get_latest_pending_otp",
    "get_otp_timer_context",
    "get_profile_role_label",
    "get_signup_lookup_payload",
    "get_user_role_level",
    "is_superadmin_user",
    "issue_email_otp",
    "map_org_role_to_profile_role",
    "map_signup_role_to_profile_role",
    "parse_decimal_score",
    "pending_student_request_queryset",
    "permission_is_grantable",
    "resolve_membership_role",
    "send_login_otp",
    "send_otp_email",
    "send_verification_otp",
    "set_student_org_request_status",
    "store_pending_registration",
    "sync_profile_pending_request_snapshot",
    "update_user_profile",
    "update_user_role",
    "user_has_any_role",
    "verify_email_otp",
    "verify_otp_code",
]
