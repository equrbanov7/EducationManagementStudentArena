"""
URL patterns for accounts app.
"""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Authentication
    path("register/", views.register_view, name="register"),
    path("verify-code/", views.verify_code_view, name="verify_code"),
    path("verify-email/", views.verify_email_link_view, name="verify_email_link"),
    path("resend-code/", views.resend_code_view, name="resend_code"),
    path("send-otp/", views.send_otp_api_view, name="send_otp_api"),
    path("verify-otp/", views.verify_otp_api_view, name="verify_otp_api"),
    path("resend-otp/", views.resend_otp_api_view, name="resend_otp_api"),
    path(
        "login/",
        views.CustomLoginView.as_view(),
        name="login",
    ),
    path("logout/", views.logout_view, name="logout"),
    # Password reset
    path(
        "password-reset/",
        views.NamespacedPasswordResetView.as_view(),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        views.NamespacedPasswordResetDoneView.as_view(),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        views.NamespacedPasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    # Dashboards
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/student/", views.student_dashboard, name="student_dashboard"),
    path("dashboard/teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    # Profile
    path("profile/", views.user_profile, name="profile"),
    path("profile/statistics/export-csv/", views.statistics_export_csv, name="statistics_export_csv"),
    # P3.1 + P3.2 — progressive enhancement endpoints. Heç bir mövcud URL
    # toxunulmur; bunlar JS-li klientlər üçün lazy-load üçündür.
    path(
        "profile/api/sections/<str:section>/",
        views.profile_section_fragment,
        name="profile_section_fragment",
    ),
    path(
        "profile/api/badges/",
        views.profile_badges_api,
        name="profile_badges_api",
    ),
    path("profile-avatar/<int:user_id>/", views.profile_avatar, name="profile_avatar"),
    # "View as" — səlahiyyətli rolların başqa istifadəçinin profilinə baxışı
    path("view-as/search/", views.view_as_search, name="view_as_search"),
    path("view-as/start/", views.view_as_start, name="view_as_start"),
    path("view-as/stop/", views.view_as_stop, name="view_as_stop"),
    path("users/<str:username>/", views.public_user_profile, name="public_profile"),
    # Role management
    path("manage-roles/", views.manage_roles, name="manage_roles"),
    # Grading
    path("grading-queue/", views.grading_queue, name="grading_queue"),
    # Assigned items
    path("assigned-exams/", views.assigned_exams, name="assigned_exams"),
    path("assigned-courses/", views.assigned_courses, name="assigned_courses"),
    path("my-results/", views.my_results, name="my_results"),
    path("pending-answers/", views.pending_answers, name="pending_answers"),
    path("my-results/<str:item_type>/<int:item_id>/", views.my_result_detail, name="my_result_detail"),
    # Pending review
    path("pending-review/", views.pending_review, name="pending_review"),
    path(
        "pending-review/<str:item_type>/<int:item_id>/",
        views.pending_review_detail,
        name="pending_review_detail",
    ),
    path("review-results/", views.review_results, name="review_results"),
    path(
        "review-results/<str:item_type>/<int:item_id>/",
        views.review_result_detail,
        name="review_result_detail",
    ),
    # RBAC management
    path("role-assignment/", views.role_assignment, name="role_assignment"),
    path(
        "student-organization-management/",
        views.student_organization_management,
        name="student_organization_management",
    ),
    path(
        "student-organization-request/",
        views.student_organization_request,
        name="student_organization_request",
    ),
    path(
        "student-organization-invitation/",
        views.student_org_invitation_action,
        name="student_org_invitation_action",
    ),
    path(
        "student-leave-organization/",
        views.student_leave_organization,
        name="student_leave_organization",
    ),
    path("permission-editor/", views.permission_editor, name="permission_editor"),
    # Superadmin oversight
    path("superadmin/organizations/", views.superadmin_organizations, name="superadmin_organizations"),
    path("superadmin/ai-settings/", views.superadmin_ai_settings, name="superadmin_ai_settings"),
    # Account management
    path("delete-account/", views.delete_account, name="delete_account"),
    path("superadmin/users/", views.superadmin_user_management, name="superadmin_user_management"),
    # Post management
    path("superadmin/post-management/", views.superadmin_post_management, name="superadmin_post_management"),
    path(
        "superadmin/post-management/<int:post_id>/delete/",
        views.superadmin_delete_post,
        name="superadmin_delete_post",
    ),
    path("org-post-management/", views.org_post_management, name="org_post_management"),
    path(
        "org-post-management/<int:post_id>/moderate/",
        views.org_moderate_post,
        name="org_moderate_post",
    ),
]
