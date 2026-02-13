"""
URL configuration for organizations app.
"""

from django.urls import path

from . import views

app_name = "organizations"

urlpatterns = [
    path("select/", views.select_organization, name="select"),
    path("switch/<slug:slug>/", views.switch_organization, name="switch"),
    # Sprint 6: Dashboard and management
    path("<slug:slug>/", views.organization_dashboard, name="dashboard"),
    path("<slug:slug>/structure/", views.organization_structure, name="structure"),
    path("<slug:slug>/members/", views.organization_members, name="members"),
    path("<slug:slug>/roles/", views.organization_roles, name="roles"),
    path("<slug:slug>/settings/", views.organization_settings, name="settings"),
]
