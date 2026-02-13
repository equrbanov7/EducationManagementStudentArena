"""
URL patterns for accounts app.
"""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Dashboards
    path("dashboard/teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    path("dashboard/student/", views.student_dashboard, name="student_dashboard"),
    # Profile
    path("profile/", views.user_profile, name="profile"),
    # Role management
    path("manage-roles/", views.manage_roles, name="manage_roles"),
    # Grading
    path("grading-queue/", views.grading_queue, name="grading_queue"),
]
