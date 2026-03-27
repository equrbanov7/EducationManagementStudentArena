"""
URL configuration for audit app.
"""

from django.urls import path

from . import views

app_name = "audit"

urlpatterns = [
    path("", views.audit_log_list, name="list"),
]
