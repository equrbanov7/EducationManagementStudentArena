"""Müraciətlər JSON səthi.

⚠️ Bu marşrutlar YALNIZ JSON/fayl endpoint-ləridir. Ekranın özü profil
kabinetinin bölməsi kimi açılır (sol sidebar qalır) — ayrıca tam səhifə YOXDUR.
"""

from django.urls import path

from . import views

app_name = "applications"

urlpatterns = [
    path("api/list/", views.application_list, name="list"),
    path("api/catalog/", views.application_catalog, name="catalog"),
    path("api/kpis/", views.application_kpis, name="kpis"),
    path("api/create/", views.application_create, name="create"),
    path("api/<uuid:application_id>/", views.application_detail, name="detail"),
    path("api/<uuid:application_id>/action/", views.application_action, name="action"),
    path(
        "api/<uuid:application_id>/attachments/<uuid:attachment_id>/download/",
        views.attachment_download,
        name="attachment_download",
    ),
]
