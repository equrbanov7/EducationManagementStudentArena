"""
URL configuration for organizations app.
"""

from django.urls import path

from . import group_actions, group_students, structure_actions, structure_views, views

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
    # Fakültə/kafedra "ətraflı görünüş" modalı (AJAX-only JSON fraqment).
    path(
        "<slug:slug>/structure/units/<uuid:unit_id>/",
        structure_views.organization_unit_detail,
        name="structure_unit_detail",
    ),
    # Ekran 01 «Universitet strukturu» — ağac əməlləri (JSON POST, səbəb + audit).
    path(
        "<slug:slug>/structure/tree/action/",
        structure_actions.structure_tree_action,
        name="structure_tree_action",
    ),
    # Rəhbər seçicisinin lookup-u (axtarışlı, səhifələnən) — `unit.assign_head`.
    path(
        "<slug:slug>/structure/tree/head-candidates/",
        structure_views.structure_head_candidates,
        name="structure_head_candidates",
    ),
    # Ekran 06 «Qruplar» — akademik qrup əməlləri (JSON POST, `unit.group_manage`).
    path("<slug:slug>/groups/action/", group_actions.group_action, name="group_action"),
    # Qrupun tələbə siyahısı (JSON, oxu) — «Qruplar» ekranındakı tələbə çekmecəsi.
    path("<slug:slug>/groups/<uuid:unit_id>/students/", group_students.group_students, name="group_students"),
    path("<slug:slug>/members/", views.organization_members, name="members"),
    path("<slug:slug>/roles/", views.organization_roles, name="roles"),
    path("<slug:slug>/settings/", views.organization_settings, name="settings"),
]
