"""Fənn qovluğu — YALNIZ fayl endirmə marşrutları.

Ekranların özü profil kabinetinin bölmələridir (UI agenti qurur; bölmə
slug-ları ``constants.SECTION_*``). Namespace: ``subject_folder``.
"""

from django.urls import path

from . import views

app_name = "subject_folder"

urlpatterns = [
    path("material/<uuid:material_id>/yukle/", views.material_download, name="material_download"),
    path(
        "tapsiriq-qosmasi/<uuid:attachment_id>/yukle/",
        views.task_attachment_download,
        name="task_attachment_download",
    ),
    path("gonderis-fayli/<uuid:file_id>/yukle/", views.submission_file_download, name="submission_file_download"),
]
