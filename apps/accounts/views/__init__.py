"""
Accounts views package.

This package contains all account-related views split into logical modules:
- auth.py: Authentication views (register, login, logout, verification)
- profile.py: User profile views (profile management, avatar)
- dashboard.py: Dashboard views (teacher/student dashboards, grading, results)
- roles.py: Role management views (manage roles, role assignment, permissions)
- organization.py: Organization management views (student requests, invitations)
- superadmin.py: Superadmin views (organization oversight)

All views are re-exported here for backward compatibility with existing URLs.
"""

# Account management views
from .account_management import (
    delete_account,
    superadmin_user_management,
)

# Authentication views
from .auth import (
    CustomLoginView,
    NamespacedPasswordResetConfirmView,
    NamespacedPasswordResetDoneView,
    NamespacedPasswordResetView,
    login_portal,
    logout_view,
    register_view,
    resend_code_view,
    resend_otp_api_view,
    send_otp_api_view,
    set_initial_password_view,
    verify_code_view,
    verify_email_link_view,
    verify_otp_api_view,
)

# Dashboard views
from .dashboard import (
    assigned_courses,
    assigned_exams,
    cabinet_entry,
    dashboard,
    grading_queue,
    my_result_detail,
    my_results,
    pending_answers,
    pending_review,
    pending_review_detail,
    review_result_detail,
    review_results,
    staff_cabinet_entry,
    student_cabinet_entry,
    student_dashboard,
    teacher_dashboard,
)

# Organization views
from .organization import (
    student_leave_organization,
    student_org_invitation_action,
    student_organization_management,
    student_organization_request,
)

# Post management views
from .post_management import (
    org_moderate_post,
    org_post_management,
    superadmin_delete_post,
    superadmin_post_management,
)

# Profile views
from .profile import (
    profile_avatar,
    profile_badges_api,
    profile_section_fragment,
    public_user_profile,
    statistics_export_csv,
    user_profile,
    view_as_search,
    view_as_start,
    view_as_stop,
)

# Role management views
from .roles import (
    manage_roles,
    permission_editor,
    role_assignment,
)

# Global search (⌘K command palette)
from .search import global_search

# Superadmin views
from .superadmin import (
    superadmin_ai_settings,
    superadmin_exam_rooms,
    superadmin_organizations,
)

__all__ = [
    # Authentication
    "CustomLoginView",
    "login_portal",
    "NamespacedPasswordResetView",
    "NamespacedPasswordResetDoneView",
    "NamespacedPasswordResetConfirmView",
    "register_view",
    "verify_code_view",
    "verify_email_link_view",
    "resend_code_view",
    "send_otp_api_view",
    "set_initial_password_view",
    "verify_otp_api_view",
    "resend_otp_api_view",
    "logout_view",
    # Profile
    "user_profile",
    "public_user_profile",
    "profile_avatar",
    "statistics_export_csv",
    "profile_section_fragment",
    "profile_badges_api",
    # "View as" — istifadəçi profilinə baxış
    "view_as_search",
    "view_as_start",
    "view_as_stop",
    # Global search (⌘K)
    "global_search",
    # Dashboard
    "dashboard",
    "cabinet_entry",
    "student_cabinet_entry",
    "staff_cabinet_entry",
    "teacher_dashboard",
    "student_dashboard",
    "grading_queue",
    "assigned_exams",
    "assigned_courses",
    "my_results",
    "pending_answers",
    "my_result_detail",
    "pending_review",
    "pending_review_detail",
    "review_results",
    "review_result_detail",
    # Roles
    "manage_roles",
    "role_assignment",
    "permission_editor",
    # Organization
    "student_organization_management",
    "student_organization_request",
    "student_org_invitation_action",
    "student_leave_organization",
    # Account management
    "delete_account",
    "superadmin_user_management",
    # Post management
    "superadmin_post_management",
    "superadmin_delete_post",
    "org_post_management",
    "org_moderate_post",
    # Superadmin
    "superadmin_organizations",
    "superadmin_ai_settings",
    "superadmin_exam_rooms",
]
