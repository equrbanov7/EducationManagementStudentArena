"""
URL configuration for audit app.
"""

from django.urls import path

from . import views

app_name = "audit"

urlpatterns = [
    path("", views.audit_log_list, name="list"),
    # 2026-09-08: sətir çekmecəsi (JSON) və cari filtrin CSV ixracı — hər ikisi
    # siyahı ilə EYNİ əhatə qapısından keçir (`views.can_view_audit`).
    path("export.csv", views.audit_log_export, name="export"),
    path("<uuid:pk>/detail.json", views.audit_log_detail, name="detail"),
]
