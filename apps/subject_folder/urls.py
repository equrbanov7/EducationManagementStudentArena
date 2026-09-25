"""Fənn qovluğu — fayl endirmə, kabinet əməlləri (JSON) və yoxlama çekməcəsi.

Ekranların özü profil kabinetinin bölmələridir (slug-lar ``constants.SECTION_*``,
kontekst ``apps.subject_folder.cabinet``); burada yalnız endirmə və JSON uçları var.
Namespace: ``subject_folder``.
"""

from django.urls import path

from . import views
from .web import endpoints

app_name = "subject_folder"

urlpatterns = [
    path("material/<uuid:material_id>/yukle/", views.material_download, name="material_download"),
    path(
        "tapsiriq-qosmasi/<uuid:attachment_id>/yukle/",
        views.task_attachment_download,
        name="task_attachment_download",
    ),
    path("gonderis-fayli/<uuid:file_id>/yukle/", views.submission_file_download, name="submission_file_download"),
    path("emel/", endpoints.action, name="action"),
    path("yoxlama/<uuid:submission_id>/", endpoints.review_detail, name="review_detail"),
    path("yoxlama/<uuid:submission_id>/onizleme/", endpoints.review_preview, name="review_preview"),
]
