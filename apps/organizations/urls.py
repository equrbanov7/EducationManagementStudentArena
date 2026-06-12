"""
URL configuration for organizations app.
"""

from django.urls import path

from . import structure_views, views

app_name = "organizations"

urlpatterns = [
    path("select/", views.select_organization, name="select"),
    path("switch/<slug:slug>/", views.switch_organization, name="switch"),
    # Sprint 6: Dashboard and management
    path("<slug:slug>/", views.organization_dashboard, name="dashboard"),
    path("<slug:slug>/structure/", views.organization_structure, name="structure"),
    # Fakültə və kafedralar ayrı idarə olunur (sidebar-da ayrı bölmələr).
    path("<slug:slug>/structure/faculties/", structure_views.organization_faculties, name="structure_faculties"),
    path("<slug:slug>/structure/kafedras/", structure_views.organization_kafedras, name="structure_kafedras"),
    path("<slug:slug>/members/", views.organization_members, name="members"),
    path("<slug:slug>/roles/", views.organization_roles, name="roles"),
    path("<slug:slug>/settings/", views.organization_settings, name="settings"),
]
