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

# Authentication views
from .auth import (
    CustomLoginView,
    logout_view,
    register_view,
    resend_code_view,
    verify_code_view,
    verify_email_link_view,
)

# Dashboard views
from .dashboard import (
    assigned_courses,
    assigned_exams,
    grading_queue,
    my_result_detail,
    my_results,
    pending_answers,
    pending_review,
    pending_review_detail,
    review_result_detail,
    review_results,
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

# Profile views
from .profile import (
    profile_avatar,
    public_user_profile,
    user_profile,
)

# Role management views
from .roles import (
    manage_roles,
    permission_editor,
    role_assignment,
)

# Superadmin views
from .superadmin import (
    superadmin_organizations,
)

__all__ = [
    # Authentication
    "CustomLoginView",
    "register_view",
    "verify_code_view",
    "verify_email_link_view",
    "resend_code_view",
    "logout_view",
    # Profile
    "user_profile",
    "public_user_profile",
    "profile_avatar",
    # Dashboard
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
    # Superadmin
    "superadmin_organizations",
]
