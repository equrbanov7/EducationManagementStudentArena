"""Elanlar marşrutları — ``/elanlar/``.

İstifadəçi ekranı kabinet bölməsidir (``/accounts/profile/?section=announcements``); burada
yalnız JSON/fayl uçları, paylaşılan qısa link və menecerin idarə səhifələri var.
"""

from django.urls import path

from . import views

app_name = "announcements"

urlpatterns = [
    path("api/list/", views.list_fragment, name="list"),
    path("api/popup/seen/", views.popup_seen, name="popup_seen"),
    path("api/<uuid:announcement_id>/read/", views.mark_read, name="read"),
    path("api/<uuid:announcement_id>/apply/", views.apply, name="apply"),
    path(
        "api/<uuid:announcement_id>/files/<uuid:attachment_id>/",
        views.attachment_download,
        name="attachment_download",
    ),
    path("idare/", views.manage_list, name="manage_list"),
    path("idare/api/rows/", views.manage_rows, name="manage_rows"),
    path("idare/yeni/", views.manage_create, name="manage_create"),
    path("idare/<uuid:announcement_id>/", views.manage_edit, name="manage_edit"),
    path("idare/<uuid:announcement_id>/emel/", views.manage_action, name="manage_action"),
    path("idare/<uuid:announcement_id>/onizleme/", views.manage_preview, name="manage_preview"),
    path("<uuid:announcement_id>/", views.detail_redirect, name="detail"),
]
