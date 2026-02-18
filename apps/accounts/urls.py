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
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path("logout/", views.logout_view, name="logout"),
    # Password reset
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(template_name="accounts/password_reset.html"),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="accounts/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(template_name="accounts/password_reset_confirm.html"),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    # Dashboards
   
    path("dashboard/student/", views.student_dashboard, name="student_dashboard"),
    path("dashboard/teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    # Profile
    path("profile/", views.user_profile, name="profile"),
    path("users/<str:username>/", views.public_user_profile, name="public_profile"),
    # Role management
    path("manage-roles/", views.manage_roles, name="manage_roles"),
    # Grading
    path("grading-queue/", views.grading_queue, name="grading_queue"),
    # Assigned items
    path("assigned-exams/", views.assigned_exams, name="assigned_exams"),
    path("assigned-courses/", views.assigned_courses, name="assigned_courses"),
    # Pending review
    path("pending-review/", views.pending_review, name="pending_review"),
    # RBAC management
    path("role-assignment/", views.role_assignment, name="role_assignment"),
    path("permission-editor/", views.permission_editor, name="permission_editor"),
]
